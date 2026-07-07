"""Analysis service — handles repo cloning, tree-sitter AST extraction, documentation, and vector indexing."""

from datetime import datetime, timezone
import os
import shutil
import subprocess
import tempfile
import fnmatch
from typing import Any, Dict, List
from sqlalchemy.orm import Session

import tree_sitter
from tree_sitter import Language, Parser
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript

from src.models.project_model import ProjectModel
from src.models.entry_model import EntryModel, EntryType
from src.models.exclusion_model import ExclusionModel
from src.models.code_document_model import CodeDocumentModel
from src.services.llm_service import LLMService

# Load Tree-sitter languages
py_lang = Language(tree_sitter_python.language())
js_lang = Language(tree_sitter_javascript.language())
ts_lang = Language(tree_sitter_typescript.language_typescript())
tsx_lang = Language(tree_sitter_typescript.language_tsx())


def get_parser_for_file(file_path: str) -> Parser | None:
    """Return a Parser initialized with the appropriate language for the file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".py":
        return Parser(py_lang)
    elif ext in (".js", ".jsx"):
        return Parser(js_lang)
    elif ext == ".ts":
        return Parser(ts_lang)
    elif ext == ".tsx":
        return Parser(tsx_lang)
    return None


class AnalysisService:
    """Orchestrates codebase cloning, parsing, documentation, and embedding indexing."""

    def __init__(self, db: Session) -> None:
        """Initialise with database session and LLM client wrapper."""
        self.db = db
        self.llm = LLMService()

    def run_analysis(self, project_id: int, entry_id: int | None = None, access_token: str | None = None, force_regenerate: bool = False) -> None:
        """Fully analyze a project repository and index it into pgvector.

        Clones the repository, parses ASTs, generates summaries, API routes,
        architecture docs, and constructs the knowledge graph.

        Args:
            project_id: Project primary key.
            entry_id: Optional entry primary key. If omitted, the first entry is used.
            access_token: Optional personal access token for private repositories.
                          Used only during cloning and never persisted.
            force_regenerate: If True, willy-nilly delete existing docs and chunks for a clean analysis.
        """
        project = self.db.query(ProjectModel).filter(ProjectModel.id == project_id).first()

        if entry_id is not None:
            entry = self.db.query(EntryModel).filter(EntryModel.id == entry_id).first()
        else:
            # Pick the first entry for the project (most recently created)
            entry = (
                self.db.query(EntryModel)
                .filter(EntryModel.project_id == project_id)
                .order_by(EntryModel.id.desc())
                .first()
            )

        if not project or not entry:
            print("Project or Entry not found for analysis.")
            return

        if not entry.repository_url:
            print("No repository URL provided.")
            return

        from src.models.analysis_run_model import AnalysisRunModel, AnalysisStatus

        # Find the analysis run record matching this run
        run_query = self.db.query(AnalysisRunModel).filter(
            AnalysisRunModel.project_id == project_id,
            AnalysisRunModel.status == AnalysisStatus.PENDING
        )
        if entry_id is not None:
            run_query = run_query.filter(AnalysisRunModel.entry_id == entry_id)
        run = run_query.order_by(AnalysisRunModel.created_at.desc()).first()

        if run:
            run.status = AnalysisStatus.RUNNING
            run.started_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(run)

        # Store force_regenerate state dynamically on analysis run model if present
        if run and getattr(run, "force_regenerate", False):
            force_regenerate = True

        # 1. Clone repository to temp directory
        # Build authenticated URL for private repos by embedding the token
        clone_url = entry.repository_url
        if access_token:
            # Supports GitHub, GitLab, Bitbucket PAT formats:
            # https://{token}@github.com/org/repo.git
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(clone_url)
            authed = parsed._replace(netloc=f"{access_token}@{parsed.netloc}")
            clone_url = urlunparse(authed)

        temp_dir = tempfile.mkdtemp(prefix="documind_")
        try:
            import os
            import shutil
            if os.path.isdir(clone_url):
                print(f"Copying local codebase from {clone_url} to {temp_dir}...")
                shutil.copytree(clone_url, temp_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"))
            else:
                print(f"Cloning {entry.repository_url} into {temp_dir}...")  # log safe URL
                cmd = ["git", "clone", "--depth", "1", clone_url, temp_dir]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # 2. Retrieve exclusion patterns
            exclusions = self.db.query(ExclusionModel).filter(
                ExclusionModel.project_id == project_id
            ).all()
            exclusion_patterns = [exc.pattern for exc in exclusions]
            # Default exclusions (centralized robust list)
            exclusion_patterns.extend([
                "node_modules", "dist", "build", ".git", ".venv", "venv",
                "__pycache__", "*.pyc", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico",
                "tests", "test", "__tests__", "spec", "docs", "*.md", "*.rst",
                ".github", ".gitlab", ".idea", ".vscode", "target", ".next", ".nuxt",
                "package-lock.json", "yarn.lock", "poetry.lock", "*_pb2.py", "generated"
            ])

            # 3. Read and Parse AST of files
            files_data = self._scan_and_parse_repo(temp_dir, exclusion_patterns)

            # 4. Generate & Save Documentation Chunks
            self._generate_and_save_docs(project_id, files_data, entry.entry_point_files, entry.repository_url, force_regenerate=force_regenerate)

            if run:
                run.status = AnalysisStatus.COMPLETED
                run.completed_at = datetime.now(timezone.utc)
                if run.started_at:
                    run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
                self.db.commit()

        except Exception as e:
            error_msg = f"Error during analysis run: {e}"
            print(error_msg)
            if run:
                run.status = AnalysisStatus.FAILED
                run.error_message = error_msg
                run.completed_at = datetime.now(timezone.utc)
                if run.started_at:
                    run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
                self.db.commit()
        finally:
            # Clean up cloned files
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _scan_and_parse_repo(self, repo_path: str, exclusion_patterns: List[str]) -> List[Dict[str, Any]]:
        """Walk the repository directory, parse source files, and extract structure details."""
        parsed_files = []
        print(f"Scanning codebase under directory: {repo_path}...")

        # Centralize standard directory name exclusions to skip walking them entirely
        SKIP_DIR_NAMES = {"node_modules", "dist", "build", ".git", ".venv", "venv", "__pycache__", "tests", "test", "__tests__", "spec", "docs", ".github", ".gitlab", ".idea", ".vscode", "target", ".next", ".nuxt", "generated"}

        for root, dirs, files in os.walk(repo_path):
            # Prune dirs in-place to avoid descending into noise directories
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIR_NAMES and not any(fnmatch.fnmatch(d, pat) or fnmatch.fnmatch(os.path.join(root, d), pat) for pat in exclusion_patterns)
            ]

            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), repo_path).replace("\\", "/")
                # Check exclusions for individual files
                if any(fnmatch.fnmatch(file, pat) or fnmatch.fnmatch(rel_path, pat) for pat in exclusion_patterns):
                    print(f"Excluded path: {rel_path}")
                    continue

                abs_file_path = os.path.join(root, file)
                
                # Check if it is a text/source file
                file_ext = os.path.splitext(file)[1].lower()
                is_src = file_ext in (
                    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".cpp", ".c", ".h",
                    ".cs", ".php", ".rb", ".json", ".yaml", ".yml", ".ini", ".conf", ".sh",
                    ".bash", ".html", ".css", ".scss", ".md"
                ) or file.lower() == "dockerfile"

                if not is_src:
                    continue  # Skip binary/unsupported files (like images, zips, binaries)

                parser = get_parser_for_file(abs_file_path)

                try:
                    print(f"Loading file: {rel_path}...")
                    # Read up to 1MB to avoid memory blow-up on massive/generated files
                    with open(abs_file_path, "r", encoding="utf-8", errors="ignore") as f:
                        code_bytes = f.read(1024 * 1024).encode("utf-8")

                    ast_summary = {"imports": [], "classes": [], "functions": []}
                    if parser:
                        print(f"Generating Tree-sitter AST for: {rel_path}")
                        tree = parser.parse(code_bytes)
                        ast_summary = self._extract_ast_nodes(tree.root_node, code_bytes)
                        print(f"AST parsed successfully for {rel_path} - Imports: {len(ast_summary['imports'])}, Classes: {len(ast_summary['classes'])}, Functions: {len(ast_summary['functions'])}")

                    parsed_files.append({
                        "file_path": rel_path,
                        "raw_code": code_bytes.decode("utf-8"),
                        "ast": ast_summary
                    })
                except Exception as ex:
                    print(f"Failed parsing file {rel_path}: {ex}")

        print(f"Codebase scan finished. Total files successfully parsed: {len(parsed_files)}")
        return parsed_files

    def _extract_ast_nodes(self, root_node: tree_sitter.Node, code_bytes: bytes) -> Dict[str, Any]:
        """Traverse tree-sitter AST and extract imports, classes, functions, and metadata."""
        imports = []
        classes = []
        functions = []

        def traverse(node: tree_sitter.Node):
            node_type = node.type
            if "import" in node_type or node_type == "import_statement" or node_type == "import_from_statement":
                try:
                    imports.append(code_bytes[node.start_byte:node.end_byte].decode("utf-8").strip())
                except:
                    pass
            elif node_type in ("class_definition", "class_declaration"):
                name_node = node.child_by_field_name("name")
                name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "UnknownClass"
                classes.append(name)
            elif node_type in ("function_definition", "function_declaration", "arrow_function", "generator_function", "method_definition", "method_signature"):
                name_node = node.child_by_field_name("name")
                name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else "anonymous"
                functions.append(name)

            for child in node.children:
                traverse(child)

        traverse(root_node)
        return {
            "imports": list(set(imports)),
            "classes": classes,
            "functions": functions
        }

    def _classify_project_type(self, files_data: List[Dict[str, Any]]) -> str:
        """Classify project type using weighted signal confidence heuristics."""
        import re
        from pathlib import Path

        # Exclude tests/docs from classification signals
        NOISE_DIRS = {"tests", "test", "docs", "migrations", "alembic", ".github", ".gitlab"}
        filtered_files = []
        for file in files_data:
            path_parts = Path(file["file_path"].lower()).parts
            if not any(part in NOISE_DIRS or part.startswith("test_") or part.endswith("_test") for part in path_parts):
                filtered_files.append(file)

        mobile_score = 0.0
        frontend_score = 0.0
        ml_score = 0.0
        backend_score = 0.0

        for file in filtered_files:
            path = file["file_path"].lower()
            code = file["raw_code"].lower()

            # Mobile indicators
            if any(x in path for x in ("androidmanifest.xml", "info.plist", "pubspec.yaml")):
                mobile_score += 2.0
            if "app.json" in path or "xcodeproj" in path:
                mobile_score += 1.5

            # Frontend indicators
            if any(x in path for x in ("package.json", "next.config", "vite.config", "webpack.config")):
                frontend_score += 2.0
            if any(path.endswith(ext) for ext in (".jsx", ".tsx", ".html", ".css", ".scss")):
                frontend_score += 1.0
            if "src/components" in path or "src/pages" in path:
                frontend_score += 1.0

            # ML / AI indicators
            if path.endswith(".ipynb") or "dataset" in path:
                ml_score += 2.0
            if any(re.search(rf"\b{re.escape(pkg)}\b", code) for pkg in ("torch", "tensorflow", "sklearn", "keras", "transformers")):
                ml_score += 1.5

            # Backend indicators
            if any(x in path for x in ("requirements.txt", "pipfile", "pom.xml", "go.mod", "cargo.toml", "dockerfile")):
                backend_score += 1.5
            if any(re.search(rf"\b{re.escape(pkg)}\b", code) for pkg in ("fastapi", "flask", "django", "express", "mongoose", "sqlalchemy")):
                backend_score += 1.5

        # Decision tree based on weighted scores
        scores = {
            "mobile": mobile_score,
            "ml_ai": ml_score,
            "frontend": frontend_score,
            "backend": backend_score
        }
        highest = max(scores, key=scores.get)

        if scores[highest] < 1.0:
            return "backend"  # default fallback

        if highest == "mobile":
            return "mobile"
        elif highest == "ml_ai":
            return "ml_ai"
        elif frontend_score >= 1.5 and backend_score >= 1.5:
            return "fullstack"
        elif highest == "frontend":
            return "frontend"
        else:
            return "backend"

    def _get_directed_context(self, files_data: List[Dict[str, Any]], doc_type: str) -> str:
        """Filter and retrieve raw code snippets matching the doc_type to provide targeted detail."""
        context_snippets = []
        doc_type_lower = doc_type.lower()
        
        for file in files_data:
            path = file["file_path"].lower()
            code = file["raw_code"].lower()
            
            include = False
            if "route" in doc_type_lower or "request_flow" in doc_type_lower:
                if any(x in path for x in ("route", "controller", "endpoint")) or any(x in code for x in ("fastapi", "apirouter", "router", "route", "flask", "django", "express")):
                    include = True
            elif "database" in doc_type_lower or "model" in doc_type_lower:
                if any(x in path for x in ("model", "schema", "db", "database")) or any(x in code for x in ("sqlalchemy", "db.model", "declarative_base", "column", "foreignkey", "table", "schema")):
                    include = True
            elif "auth" in doc_type_lower:
                if any(x in path for x in ("auth", "jwt", "login", "oauth", "token", "session")) or any(x in code for x in ("jwt", "bcrypt", "oauth2", "login", "password_hash")):
                    include = True
            elif "service" in doc_type_lower:
                if any(x in path for x in ("service", "business", "logic", "handler")) or any(x in code for x in ("service", "manager", "logic")):
                    include = True
            
            if include:
                # Include first 3000 chars of targeted files
                context_snippets.append(
                    f"### Targeted Code File: `{file['file_path']}`\n"
                    f"```python\n"
                    f"{file['raw_code'][:3000]}\n"
                    f"```"
                )
        
        return "\n\n".join(context_snippets) if context_snippets else ""

    def _generate_and_save_docs(self, project_id: int, files_data: List[Dict[str, Any]], entry_point_files: str | None, repo_url: str | None = None, force_regenerate: bool = False) -> None:
        """Use the selected LLM provider (or local fallback) to construct project-type-specific documentation."""
        from src.config import get_settings
        settings = get_settings()

        # Check if LLM API key is present
        api_key = None
        if self.llm.provider == "gemini":
            api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        elif self.llm.provider == "openai":
            api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        elif self.llm.provider == "nvidia":
            api_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY")

        use_llm = api_key is not None and len(api_key.strip()) > 0

        # Classify Project Type, respecting user override if set
        from src.models.project_model import ProjectModel
        project_obj = self.db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        saved_project_type = project_obj.project_type if project_obj else None

        project_type = saved_project_type or self._classify_project_type(files_data)
        if project_obj and not project_obj.project_type:
            project_obj.project_type = project_type
            self.db.add(project_obj)
            self.db.commit()
        print(f"Classified project type: {project_type.upper()}")

        # Check if we should resume a failed/aborted run, or do a fresh generation
        from src.models.analysis_run_model import AnalysisRunModel, AnalysisStatus
        
        # Look for the last non-pending/non-running run
        last_run = self.db.query(AnalysisRunModel).filter(
            AnalysisRunModel.project_id == project_id,
            AnalysisRunModel.status != AnalysisStatus.PENDING,
            AnalysisRunModel.status != AnalysisStatus.RUNNING
        ).order_by(AnalysisRunModel.created_at.desc()).first()

        is_resume = last_run is not None and last_run.status == AnalysisStatus.FAILED and not force_regenerate
        
        existing_docs = {}
        if is_resume:
            print("FAILED run detected. Resuming and keeping existing generated documentation chunks...")
            existing_docs = {d.document_type: d for d in self.db.query(CodeDocumentModel).filter(CodeDocumentModel.project_id == project_id).all()}
        else:
            print("Starting fresh documentation generation. Clearing old documents...")
            self.db.query(CodeDocumentModel).filter(CodeDocumentModel.project_id == project_id).delete()
            self.db.commit()

        # Define documents structure by project type
        doc_structures = {
            "backend": [
                ("project_summary", "Project Summary"),
                ("architecture", "Backend Architecture"),
                ("routes", "API Routes"),
                ("events", "Events"),
                ("services", "Services & Business Logic"),
                ("database_models", "Database Models"),
                ("auth_flow", "Authentication & Authorization"),
                ("external_integrations", "External Integrations"),
                ("packages", "Packages & Dependencies"),
                ("file_explanations", "File Explanations"),
                ("environment_variables", "Environment Variables"),
                ("request_flow", "Request Flow")
            ],
            "frontend": [
                ("project_summary", "Project Summary"),
                ("architecture", "Frontend Architecture"),
                ("pages", "Pages"),
                ("components", "Components"),
                ("ui_flow", "UI Flow"),
                ("state_management", "State Management"),
                ("api_integrations", "API Integrations"),
                ("packages", "Packages & Dependencies"),
                ("file_explanations", "File Explanations"),
                ("routing_structure", "Routing Structure")
            ],
            "fullstack": [
                ("project_summary", "Project Summary"),
                ("system_architecture", "System Architecture"),
                ("frontend_architecture", "Frontend Architecture"),
                ("backend_architecture", "Backend Architecture"),
                ("routes", "API Routes"),
                ("events", "Events"),
                ("database_models", "Database Models"),
                ("pages", "Pages"),
                ("components", "Components"),
                ("services", "Services"),
                ("auth_flow", "Authentication Flow"),
                ("data_flow", "Data Flow"),
                ("packages", "Packages/Dependencies"),
                ("file_explanations", "File Explanations")
            ],
            "ml_ai": [
                ("project_summary", "Project Summary"),
                ("architecture", "Architecture Overview"),
                ("dataset_analysis", "Dataset Analysis"),
                ("model_architecture", "Model Architecture"),
                ("training_pipeline", "Training Pipeline"),
                ("inference_pipeline", "Inference Pipeline"),
                ("evaluation_metrics", "Evaluation Metrics"),
                ("packages", "Packages/Dependencies"),
                ("file_explanations", "File Explanations")
            ],
            "mobile": [
                ("project_summary", "Project Summary"),
                ("screens", "Screens"),
                ("navigation_flow", "Navigation Flow"),
                ("state_management", "State Management"),
                ("api_integrations", "API Integrations"),
                ("local_storage", "Local Storage"),
                ("packages", "Packages/Dependencies"),
                ("file_explanations", "File Explanations")
            ]
        }

        target_docs = doc_structures.get(project_type, doc_structures["backend"])
        codebase_summary_context = []

        # Local AST File summary creation
        print("Parsing files AST...")
        for file in files_data:
            # Provide the AST structure AND actual code snippet context to prevent LLM hallucinations
            file_ast_summary = (
                f"### File: `{file['file_path']}`\n"
                f"- **Classes**: {', '.join(file['ast']['classes']) if file['ast']['classes'] else 'None'}\n"
                f"- **Functions**: {', '.join(file['ast']['functions']) if file['ast']['functions'] else 'None'}\n"
                f"- **Imports**: {', '.join(file['ast']['imports']) if file['ast']['imports'] else 'None'}\n"
                f"- **Code Content (First 4000 chars)**:\n"
                f"```python\n"
                f"{file['raw_code'][:4000]}\n"
                f"```\n"
            )
            codebase_summary_context.append(file_ast_summary)

            # File Explanation Document (only write if missing)
            if "file_detail" not in existing_docs or not any(d.file_path == file["file_path"] for d in self.db.query(CodeDocumentModel).filter(CodeDocumentModel.project_id == project_id, CodeDocumentModel.document_type == "file_detail").all()):
                file_summary_content = (
                    f"## Functional Details for `{file['file_path']}`\n"
                    f"This file was analyzed structurally. Imports: {file['ast']['imports']}\n"
                    f"Classes defined: {file['ast']['classes']}\n"
                    f"Functions defined: {file['ast']['functions']}"
                )
                doc = CodeDocumentModel(
                    project_id=project_id,
                    file_path=file["file_path"],
                    document_type="file_detail",
                    title=f"File: {file['file_path']}",
                    content=file_summary_content,
                    embedding=None
                )
                self.db.add(doc)

            # Chunk and embed file contents if it is a source file
            file_ext = os.path.splitext(file["file_path"])[1].lower()
            is_src = file_ext in (
                ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".cpp", ".c", ".h",
                ".cs", ".php", ".rb", ".json", ".yaml", ".yml", ".ini", ".conf", ".sh",
                ".bash", ".html", ".css", ".scss", ".md"
            ) or file["file_path"].lower() == "dockerfile"
            
            if is_src:
                has_chunks = False
                if is_resume:
                    has_chunks = self.db.query(CodeDocumentModel).filter(
                        CodeDocumentModel.project_id == project_id,
                        CodeDocumentModel.document_type == "code_chunk",
                        CodeDocumentModel.file_path == file["file_path"]
                    ).first() is not None
                
                if not has_chunks:
                    print(f"Chunking and embedding source file: {file['file_path']}...")
                    chunks = []
                    raw_text = file["raw_code"]
                    chunk_size = 1000
                    overlap = 200
                    if len(raw_text) <= chunk_size:
                        chunks = [raw_text]
                    else:
                        start = 0
                        while start < len(raw_text):
                            end = start + chunk_size
                            chunks.append(raw_text[start:end])
                            start += chunk_size - overlap
                    
                    for idx, chunk_content in enumerate(chunks):
                        emb = None
                        if use_llm:
                            try:
                                emb = self.llm.generate_embedding(chunk_content)
                            except Exception as emb_ex:
                                print(f"Chunk embedding error for {file['file_path']}: {emb_ex}. Using zero vector.")
                                emb = [0.0] * 4096
                        
                        chunk_doc = CodeDocumentModel(
                            project_id=project_id,
                            file_path=file["file_path"],
                            document_type="code_chunk",
                            title=f"Code Chunk: {file['file_path']} (Part {idx + 1})",
                            content=chunk_content,
                            embedding=emb
                        )
                        self.db.add(chunk_doc)
        self.db.commit()

        summary_block = ""
        entry_points_info = entry_point_files if entry_point_files else "Not specified"
        
        # Determine if we should use Map-Reduce Hierarchical Summarization based on codebase scale
        if len(files_data) <= 3 or not use_llm:
            print("Small codebase detected. Using direct file code previews in context.")
            summary_block = "\n".join(codebase_summary_context)
        else:
            print(f"Large codebase detected ({len(files_data)} files). Running Map-Reduce Hierarchical Summarization...")
            # Group files by directory
            from collections import defaultdict
            folders = defaultdict(list)
            for file in files_data:
                folder_path = os.path.dirname(file["file_path"]) or "root"
                folders[folder_path].append(file)
            
            folder_summaries = []
            # Build description blocks of all folders
            all_folders_desc = []
            for folder, folder_files in folders.items():
                folder_desc_list = []
                for f in folder_files:
                    folder_desc_list.append(
                        f"  - File: `{f['file_path']}` (Classes: {f['ast']['classes']}, Functions: {f['ast']['functions']}, Imports: {f['ast']['imports']})"
                    )
                all_folders_desc.append(f"Directory: `{folder}`\n" + "\n".join(folder_desc_list))
            
            all_folders_block = "\n\n".join(all_folders_desc)
            prompt_folders = (
                f"You are a software architect summarizing codebase directories.\n"
                f"For each of the directories listed below, write a 2-sentence summary of its technical responsibilities.\n"
                f"Structure your response exactly like this for each directory (use this exact header template):\n"
                f"=== DIRECTORY: directory_name ===\n"
                f"[Your 2-sentence summary here]\n\n"
                f"Directories to summarize:\n{all_folders_block}"
            )
            
            print("Summarizing all module folders in a single batch LLM request to conserve rate limits...")
            try:
                batch_response = self.llm.generate_text(prompt_folders, "You are a software architect summarizing module folders.")
                chunks = batch_response.split("=== DIRECTORY:")
                for chunk in chunks:
                    if not chunk.strip():
                        continue
                    try:
                        header, body = chunk.split("===", 1)
                        folder_name = header.strip()
                        folder_summary_body = body.strip()
                        folder_summaries.append(f"### Directory: `{folder_name}`\n{folder_summary_body}")
                    except Exception as parse_err:
                        print(f"Error parsing batch folder summary chunk: {parse_err}")
            except Exception as batch_err:
                print(f"Failed batch folder summaries: {batch_err}. Falling back to simple file lists.")
                for folder, folder_files in folders.items():
                    folder_summaries.append(f"### Directory: `{folder}`\nContains code files: {', '.join(f['file_path'] for f in folder_files)}")

            # Include raw code of entry points so the LLM gets the entry context
            entry_points_code = []
            entry_list = [f.strip() for f in entry_points_info.split(",")] if entry_point_files else []
            for file in files_data:
                if file["file_path"] in entry_list or any(x in file["file_path"].lower() for x in ("main.py", "app.py", "index.ts", "server.ts", "server.js", "app.js")):
                    entry_points_code.append(
                        f"### Entry Point Code: `{file['file_path']}`\n"
                        f"```python\n"
                        f"{file['raw_code'][:4000]}\n"
                        f"```"
                    )
            
            summary_block = (
                "## Hierarchical Module Summaries\n" +
                "\n\n".join(folder_summaries) +
                "\n\n## Entry Point Source Code\n" +
                "\n\n".join(entry_points_code)
            )

        # Extract repo name for semantic indexing context
        repo_name = ""
        if repo_url:
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            print(f"Extracted Repository Name context: {repo_name}")

        # 2. Knowledge Graph Generation (stored separately)
        if "knowledge_graph" not in existing_docs:
            print("Constructing Knowledge Graph...")
            kg_content = f"## Knowledge Graph for Project\n\n### Code Nodes:\n"
            for file in files_data:
                kg_content += f"- **Node**: `{file['file_path']}` (Classes: {len(file['ast']['classes'])}, Functions: {len(file['ast']['functions'])})\n"
            kg_content += "\n### Import Relationships:\n"
            edge_count = 0
            for file in files_data:
                for imp in file['ast']['imports']:
                    for other_file in files_data:
                        base_other = os.path.splitext(other_file['file_path'])[0]
                        if base_other in imp or base_other.replace("/", ".") in imp:
                            kg_content += f"- `{file['file_path']}` ---> imports ---> `{other_file['file_path']}`\n"
                            edge_count += 1
                            break
            if edge_count == 0:
                kg_content += "No internal file import links resolved statically."
            self._save_project_doc(project_id, "knowledge_graph", "Project Knowledge Graph", kg_content, False)

        # Filter target docs list to only generate the ones that are missing
        docs_to_generate = [(doc_type, title) for doc_type, title in target_docs if doc_type not in existing_docs]

        # 3. Generating Project Documentation
        if not docs_to_generate:
            print("All project documents are already generated. Skipping LLM request.")
            return
        
        if use_llm:
            for doc_type, title in docs_to_generate:
                try:
                    print(f"Generating dynamic documentation via LLM for section: {title} ({doc_type})...")
                    
                    # Instruct LLM to generate exactly ONE specific document
                    extra_instruction = ""
                    if doc_type == "architecture":
                        extra_instruction = "\nFor this Architecture document, you MUST include a clean, detailed System Architecture Diagram represented in Mermaid markdown format (using '```mermaid' language block) representing the component connections and data flow."
                    elif doc_type == "request_flow":
                        extra_instruction = "\nPlease structure this document clearly to show a step-by-step example flow (e.g. Request -> Controller -> Service -> Repository -> Database) matching the actual code calls."

                    # Retrieve targeted context snippets for this specific document type (Directed Retrieval)
                    directed_context = self._get_directed_context(files_data, doc_type)
                    directed_context_str = f"\n\n## Targeted Code Context:\n{directed_context}\n" if directed_context else ""

                    prompt = (
                        f"You are a premium software documenter. Analyze this {project_type} codebase.\n"
                        f"Repository Name: {repo_name}\n"
                        f"Repository URL: {repo_url if repo_url else 'Not specified'}\n"
                        f"Entry points: {entry_points_info}.\n\n"
                        f"Codebase Structure Context:\n{summary_block}{directed_context_str}\n\n"
                        f"You MUST generate a comprehensive documentation document titled '{title}' (Type: {doc_type}) for this codebase.{extra_instruction}\n\n"
                        f"CRITICAL RULES:\n"
                        f"1. ONLY generate the content for this specific document: '{title}'.\n"
                        f"2. Do NOT generate any other sections or document titles.\n"
                        f"3. Do NOT output any delimiters like '=== DOCUMENT:' or document wrappers."
                    )
                    
                    system_instruction = (
                        "You are an extremely precise software architect documenting a codebase. "
                        "CRITICAL DIRECTION: Rely ONLY on the verified evidence provided in the codebase structure context (Imports, Classes, Functions, and raw snippets). "
                        "DO NOT assume, guess, or hallucinate implementation details. If a class or function is listed but its full code is not provided, "
                        "describe what it is signature-wise, and explicitly state that the inner details/algorithms are not observed in the context. "
                        "Never suggest algorithms, patterns, or libraries (e.g., SolvePnP, Kalman filters, databases) unless they are explicitly present in the imports or code snippets. "
                        "The actual source code contents, imports, and structure are the ABSOLUTE GROUND TRUTH. The Repository Name is a minor semantic hint and must be treated with low weight. "
                        "If the codebase has evolved beyond the repository name (e.g., repository is named 'blink-detection' but the code does general face mesh or retina scanning), "
                        "you MUST document the actual features and logic present in the code, completely overriding any assumptions from the repository name. "
                        "ONLY generate the requested single section. Do not output any delimiters, headers, or other chapters. "
                        "Accuracy is paramount."
                    )
                    
                    doc_content = self.llm.generate_text(prompt, system_instruction)
                    self._save_project_doc(project_id, doc_type, title, doc_content.strip(), True)
                    print(f"Successfully saved generated document: {title}")
                except Exception as doc_err:
                    print(f"Failed to generate document '{title}': {doc_err}")
        else:
            print("Generating local fallback documentation documents...")
            for doc_type, title in docs_to_generate:
                fallback_content = (
                    f"## {title}\n"
                    f"*(Documentation generated locally due to offline fallback)*\n\n"
                    f"### Component Data:\n"
                    f"- Project Type: {project_type.upper()}\n"
                    f"- Entry Point Files: {entry_points_info}\n"
                    f"- Mapped files: {len(files_data)}\n"
                )
                self._save_project_doc(project_id, doc_type, title, fallback_content, False)

        # Calculate and save project stats and technologies stack
        stats_dict = self._calculate_project_stats(files_data, project_type)
        tech_stack = self._extract_technology_stack(files_data)
        
        from src.models.project_model import ProjectModel
        project = self.db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if project:
            project.stats = stats_dict
            project.technology_stack = tech_stack
            self.db.add(project)
            self.db.commit()
            print(f"Successfully saved project stats: {stats_dict}")
            print(f"Successfully saved technology stack: {tech_stack}")

    def _calculate_project_stats(self, files_data: List[Dict[str, Any]], project_type: str) -> Dict[str, Any]:
        """Calculate counts for files, lines of code, classes, functions, routes, models, etc. using AST hints."""
        from pathlib import Path

        # Exclude directories / files that are noise
        NOISE_DIRS = {"tests", "test", "docs", "migrations", "alembic", ".github", ".gitlab", "venv", ".venv", "node_modules", "dist", "build"}
        
        filtered_files = []
        for file in files_data:
            path_parts = Path(file["file_path"].lower()).parts
            # If any part of the path is in noise directories, skip it
            if any(part in NOISE_DIRS or part.startswith("test_") or part.endswith("_test") for part in path_parts):
                continue
            filtered_files.append(file)

        total_files = len(filtered_files)
        total_loc = sum(len(f["raw_code"].splitlines()) for f in filtered_files)
        total_functions = sum(len(f["ast"]["functions"]) for f in filtered_files)
        total_classes = sum(len(f["ast"]["classes"]) for f in filtered_files)

        routes_count = 0
        services_count = 0
        models_count = 0
        pages_count = 0
        components_count = 0
        datasets_count = 0

        for file in filtered_files:
            path = file["file_path"].lower()
            code = file["raw_code"].lower()
            ast = file.get("ast", {})
            classes = ast.get("classes", [])
            functions = ast.get("functions", [])
            imports = ast.get("imports", [])

            # Route counting: Functions in files containing route decorations, or explicitly mapped routes
            is_route_file = any(x in path for x in ("route", "controller", "endpoint", "handler", "/api/")) or path.startswith("api/")
            has_route_imports = any("fastapi" in imp.lower() or "apirouter" in imp.lower() or "blueprint" in imp.lower() or "express" in imp.lower() for imp in imports)
            if is_route_file or has_route_imports:
                # Count functions in controllers / routers as routes
                routes_count += len(functions)

            # Model counting: Classes in files matching model/schema, or importing SQLAlchemy/Pydantic
            is_model_file = any(x in path for x in ("model", "schema", "db", "entity"))
            has_model_imports = any("sqlalchemy" in imp.lower() or "pydantic" in imp.lower() or "declarative_base" in imp.lower() or "drizzle" in imp.lower() or "mongoose" in imp.lower() for imp in imports)
            if is_model_file or has_model_imports:
                models_count += len(classes)

            # Service layer counting
            if "service" in path or "logic" in path:
                services_count += 1

            # Page/Screen counting
            if any(x in path for x in ("page", "screen", "view")):
                pages_count += 1

            # Components counting (avoiding tests and packages)
            if any(x in path for x in ("component", "widget", "ui")):
                components_count += 1

            # Datasets counting
            if "dataset" in path or "data" in path or path.endswith(".ipynb"):
                datasets_count += 1

        return {
            "files": total_files,
            "lines_of_code": total_loc,
            "functions": total_functions,
            "classes": total_classes,
            "routes": routes_count,
            "services": services_count,
            "models": models_count,
            "pages": pages_count,
            "components": components_count,
            "datasets": datasets_count,
        }

    def _extract_technology_stack(self, files_data: List[Dict[str, Any]]) -> List[str]:
        """Analyze imports, packages, and code context to detect technologies used with high accuracy."""
        import re
        from pathlib import Path

        # Exclude directories / files that are noise
        NOISE_DIRS = {"tests", "test", "docs", "migrations", "alembic", ".github", ".gitlab", "venv", ".venv", "node_modules", "dist", "build"}
        
        filtered_files = []
        for file in files_data:
            path_parts = Path(file["file_path"].lower()).parts
            # If any part of the path is in noise directories, skip it
            if any(part in NOISE_DIRS or part.startswith("test_") or part.endswith("_test") for part in path_parts):
                continue
            filtered_files.append(file)

        # Mapping of import packages or dependency names to display tech names
        # Note: keys are lowercase package/module names to search for with word boundaries
        PACKAGE_TO_TECH = {
            "fastapi": "FastAPI",
            "flask": "Flask",
            "django": "Django",
            "express": "Express",
            "pymongo": "MongoDB",
            "motor": "MongoDB",
            "mongodb": "MongoDB",
            "sqlalchemy": "SQLAlchemy (implies PostgreSQL/MySQL/SQLite)",
            "postgresql": "PostgreSQL",
            "postgres": "PostgreSQL",
            "psycopg2": "PostgreSQL",
            "psycopg": "PostgreSQL",
            "sqlite3": "SQLite",
            "sqlite": "SQLite",
            "redis": "Redis",
            "boto3": "AWS S3",
            "slack_sdk": "Slack",
            "slack": "Slack",
            "react": "React",
            "vue": "Vue",
            "angular": "Angular",
            "next": "Next.js",
            "torch": "PyTorch",
            "tensorflow": "TensorFlow",
            "sklearn": "Scikit-Learn",
            "scikit-learn": "Scikit-Learn",
        }

        # Scan for dependency manifests first (strong signals)
        manifest_techs = set()
        for file in filtered_files:
            fname = Path(file["file_path"]).name.lower()
            if fname in {"requirements.txt", "package.json", "pyproject.toml", "go.mod", "cargo.toml", "pom.xml"}:
                code = file["raw_code"].lower()
                for pkg, tech in PACKAGE_TO_TECH.items():
                    # Word boundary search to avoid sub-string matches like "fastapi_utils" matching "fastapi"
                    # or other common naming overlaps.
                    if re.search(rf"\b{re.escape(pkg)}\b", code):
                        manifest_techs.add(tech)

        # Scan for code imports / configurations (secondary signals)
        import_techs = set()
        for file in filtered_files:
            file_path = file["file_path"].lower()
            code = file["raw_code"].lower()

            # Inspect AST-parsed imports or explicit statements
            ast_imports = file.get("ast", {}).get("imports", [])
            for imp in ast_imports:
                imp_lower = imp.lower()
                for pkg, tech in PACKAGE_TO_TECH.items():
                    if re.search(rf"\b{re.escape(pkg)}\b", imp_lower):
                        import_techs.add(tech)

            # Extra specific checks
            if file_path.endswith("package.json"):
                for pkg, tech in [("react", "React"), ("vue", "Vue"), ("angular", "Angular"), ("next", "Next.js"), ("express", "Express")]:
                    if re.search(rf'"{re.escape(pkg)}"', code):
                        import_techs.add(tech)

            if "dockerfile" in file_path or "docker-compose" in file_path:
                import_techs.add("Docker")

        # Combine results:
        # If we have manifests (requirements.txt, package.json etc.), prioritize them
        if manifest_techs:
            return list(manifest_techs)
        
        return list(import_techs)

    def _save_project_doc(self, project_id: int, doc_type: str, title: str, content: str, embed: bool) -> None:
        """Embed and save project level documents."""
        embedding_val = None
        if embed:
            try:
                embedding_val = self.llm.generate_embedding(content)
            except Exception as e:
                print(f"Embedding generation error: {e}. Defaulting to zero vector.")
                # Safe zero vector of dimension 4096 to prevent pgvector constraints mismatch
                embedding_val = [0.0] * 4096

        doc = CodeDocumentModel(
            project_id=project_id,
            file_path=None,
            document_type=doc_type,
            title=title,
            content=content,
            embedding=embedding_val
        )
        self.db.add(doc)
        self.db.commit()

    def regenerate_single_document(self, project_id: int, document_type: str, access_token: str | None = None) -> CodeDocumentModel:
        """Regenerate a single document for a project by re-cloning and re-analyzing the repository.
        
        Args:
            project_id: Project primary key.
            document_type: The document type to regenerate.
            access_token: Optional personal access token for private repositories.
        """
        project = self.db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise ValueError("Project not found.")

        # Pick the most recent entry for the project
        entry = (
            self.db.query(EntryModel)
            .filter(EntryModel.project_id == project_id)
            .order_by(EntryModel.id.desc())
            .first()
        )

        if not entry or not entry.repository_url:
            raise ValueError("No repository associated with this project.")

        from src.config import get_settings
        settings = get_settings()

        # Check if LLM API key is present
        api_key = None
        if self.llm.provider == "gemini":
            api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        elif self.llm.provider == "openai":
            api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
        elif self.llm.provider == "nvidia":
            api_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY")

        use_llm = api_key is not None and len(api_key.strip()) > 0
        if not use_llm:
            raise ValueError("No LLM API key configured. Cannot regenerate document.")

        clone_url = entry.repository_url
        if access_token:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(clone_url)
            authed = parsed._replace(netloc=f"{access_token}@{parsed.netloc}")
            clone_url = urlunparse(authed)

        temp_dir = tempfile.mkdtemp(prefix="documind_")
        try:
            import os
            import shutil
            if os.path.isdir(clone_url):
                print(f"Copying local codebase from {clone_url} to {temp_dir} for regeneration of '{document_type}'...")
                shutil.copytree(clone_url, temp_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"))
            else:
                print(f"Cloning {entry.repository_url} into {temp_dir} for regeneration of '{document_type}'...")
                cmd = ["git", "clone", "--depth", "1", clone_url, temp_dir]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Retrieve exclusion patterns
            exclusions = self.db.query(ExclusionModel).filter(
                ExclusionModel.project_id == project_id
            ).all()
            exclusion_patterns = [exc.pattern for exc in exclusions]
            exclusion_patterns.extend([
                "node_modules", "dist", "build", ".git", ".venv", "venv",
                "__pycache__", "*.pyc", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico"
            ])

            # Scan and parse files
            files_data = self._scan_and_parse_repo(temp_dir, exclusion_patterns)
            project_type = self._classify_project_type(files_data)

            # Determine title for the document type
            doc_titles = {
                "project_summary": "Project Summary",
                "architecture": "System Architecture" if project_type == "fullstack" else "Architecture Overview" if project_type == "ml_ai" else "Frontend Architecture" if project_type == "frontend" else "Backend Architecture",
                "routes": "API Routes",
                "services": "Services & Business Logic" if project_type == "backend" else "Services",
                "database_models": "Database Models",
                "auth_flow": "Authentication & Authorization" if project_type == "backend" else "Authentication Flow",
                "external_integrations": "External Integrations",
                "packages": "Packages & Dependencies" if project_type in ("backend", "frontend") else "Packages/Dependencies",
                "file_explanations": "File Explanations",
                "environment_variables": "Environment Variables",
                "request_flow": "Request Flow",
                "pages": "Pages",
                "components": "Components",
                "ui_flow": "UI Flow",
                "state_management": "State Management",
                "api_integrations": "API Integrations",
                "routing_structure": "Routing Structure",
                "system_architecture": "System Architecture",
                "frontend_architecture": "Frontend Architecture",
                "backend_architecture": "Backend Architecture",
                "data_flow": "Data Flow",
                "dataset_analysis": "Dataset Analysis",
                "model_architecture": "Model Architecture",
                "training_pipeline": "Training Pipeline",
                "inference_pipeline": "Inference Pipeline",
                "evaluation_metrics": "Evaluation Metrics",
                "screens": "Screens",
                "navigation_flow": "Navigation Flow",
                "local_storage": "Local Storage"
            }
            title = doc_titles.get(document_type, document_type.replace("_", " ").title())

            # Build summary_block
            codebase_summary_context = []
            for file in files_data:
                file_ast_summary = (
                    f"### File: `{file['file_path']}`\n"
                    f"- **Classes**: {', '.join(file['ast']['classes']) if file['ast']['classes'] else 'None'}\n"
                    f"- **Functions**: {', '.join(file['ast']['functions']) if file['ast']['functions'] else 'None'}\n"
                    f"- **Imports**: {', '.join(file['ast']['imports']) if file['ast']['imports'] else 'None'}\n"
                    f"- **Code Content (First 4000 chars)**:\n"
                    f"```python\n"
                    f"{file['raw_code'][:4000]}\n"
                    f"```\n"
                )
                codebase_summary_context.append(file_ast_summary)

            entry_points_info = entry.entry_point_files if entry.entry_point_files else "Not specified"
            if len(files_data) <= 3:
                summary_block = "\n".join(codebase_summary_context)
            else:
                from collections import defaultdict
                folders = defaultdict(list)
                for file in files_data:
                    folder_path = os.path.dirname(file["file_path"]) or "root"
                    folders[folder_path].append(file)
                
                folder_summaries = []
                all_folders_desc = []
                for folder, folder_files in folders.items():
                    folder_desc_list = []
                    for f in folder_files:
                        folder_desc_list.append(
                            f"  - File: `{f['file_path']}` (Classes: {f['ast']['classes']}, Functions: {f['ast']['functions']}, Imports: {f['ast']['imports']})"
                        )
                    all_folders_desc.append(f"Directory: `{folder}`\n" + "\n".join(folder_desc_list))
                
                all_folders_block = "\n\n".join(all_folders_desc)
                prompt_folders = (
                    f"You are a software architect summarizing codebase directories.\n"
                    f"For each of the directories listed below, write a 2-sentence summary of its technical responsibilities.\n"
                    f"Structure your response exactly like this for each directory (use this exact header template):\n"
                    f"=== DIRECTORY: directory_name ===\n"
                    f"[Your 2-sentence summary here]\n\n"
                    f"Directories to summarize:\n{all_folders_block}"
                )
                
                try:
                    batch_response = self.llm.generate_text(prompt_folders, "You are a software architect summarizing module folders.")
                    chunks = batch_response.split("=== DIRECTORY:")
                    for chunk in chunks:
                        if not chunk.strip():
                            continue
                        try:
                            header, body = chunk.split("===", 1)
                            folder_name = header.strip()
                            folder_summary_body = body.strip()
                            folder_summaries.append(f"### Directory: `{folder_name}`\n{folder_summary_body}")
                        except Exception as parse_err:
                            print(f"Error parsing batch folder summary chunk: {parse_err}")
                except Exception as batch_err:
                    print(f"Failed batch folder summaries: {batch_err}. Falling back to simple file lists.")
                    for folder, folder_files in folders.items():
                        folder_summaries.append(f"### Directory: `{folder}`\nContains code files: {', '.join(f['file_path'] for f in folder_files)}")

                entry_points_code = []
                entry_list = [f.strip() for f in entry_points_info.split(",")] if entry.entry_point_files else []
                for file in files_data:
                    if file["file_path"] in entry_list or any(x in file["file_path"].lower() for x in ("main.py", "app.py", "index.ts", "server.ts", "server.js", "app.js")):
                        entry_points_code.append(
                            f"### Entry Point Code: `{file['file_path']}`\n"
                            f"```python\n"
                            f"{file['raw_code'][:4000]}\n"
                            f"```"
                        )
                
                summary_block = (
                    "## Hierarchical Module Summaries\n" +
                    "\n\n".join(folder_summaries) +
                    "\n\n## Entry Point Source Code\n" +
                    "\n\n".join(entry_points_code)
                )

            repo_name = ""
            if entry.repository_url:
                repo_name = entry.repository_url.split("/")[-1].replace(".git", "")

            # Generate the document content via LLM
            extra_instruction = ""
            if document_type == "architecture":
                extra_instruction = "\nFor this Architecture document, you MUST include a clean, detailed System Architecture Diagram represented in Mermaid markdown format (using '```mermaid' language block) representing the component connections and data flow."
            elif document_type == "request_flow":
                extra_instruction = "\nPlease structure this document clearly to show a step-by-step example flow (e.g. Request -> Controller -> Service -> Repository -> Database) matching the actual code calls."

            directed_context = self._get_directed_context(files_data, document_type)
            directed_context_str = f"\n\n## Targeted Code Context:\n{directed_context}\n" if directed_context else ""

            prompt = (
                f"You are a premium software documenter. Analyze this {project_type} codebase.\n"
                f"Repository Name: {repo_name}\n"
                f"Repository URL: {entry.repository_url}\n"
                f"Entry points: {entry_points_info}.\n\n"
                f"Codebase Structure Context:\n{summary_block}{directed_context_str}\n\n"
                f"You MUST generate a comprehensive documentation document titled '{title}' (Type: {document_type}) for this codebase.{extra_instruction}\n\n"
                f"CRITICAL RULES:\n"
                f"1. ONLY generate the content for this specific document: '{title}'.\n"
                f"2. Do NOT generate any other sections or document titles.\n"
                f"3. Do NOT output any delimiters like '=== DOCUMENT:' or document wrappers."
            )
            
            system_instruction = (
                "You are an extremely precise software architect documenting a codebase. "
                "CRITICAL DIRECTION: Rely ONLY on the verified evidence provided in the codebase structure context (Imports, Classes, Functions, and raw snippets). "
                "DO NOT assume, guess, or hallucinate implementation details. If a class or function is listed but its full code is not provided, "
                "describe what it is signature-wise, and explicitly state that the inner details/algorithms are not observed in the context. "
                "Never suggest algorithms, patterns, or libraries (e.g., SolvePnP, Kalman filters, databases) unless they are explicitly present in the imports or code snippets. "
                "The actual source code contents, imports, and structure are the ABSOLUTE GROUND TRUTH. The Repository Name is a minor semantic hint and must be treated with low weight. "
                "If the codebase has evolved beyond the repository name (e.g., repository is named 'blink-detection' but the code does general face mesh or retina scanning), "
                "you MUST document the actual features and logic present in the code, completely overriding any assumptions from the repository name. "
                "ONLY generate the requested single section. Do not output any delimiters, headers, or other chapters. "
                "Accuracy is paramount."
            )

            doc_content = self.llm.generate_text(prompt, system_instruction)
            if doc_content.startswith("Error during generation"):
                raise ValueError(doc_content)

            # Generate embedding
            embedding_val = None
            try:
                embedding_val = self.llm.generate_embedding(doc_content)
            except Exception as emb_ex:
                print(f"Embedding error: {emb_ex}. Using zero vector.")
                embedding_val = [0.0] * 4096

            # Delete old document of same type
            self.db.query(CodeDocumentModel).filter(
                CodeDocumentModel.project_id == project_id,
                CodeDocumentModel.document_type == document_type
            ).delete()
            self.db.commit()

            # Save new document
            doc = CodeDocumentModel(
                project_id=project_id,
                file_path=None,
                document_type=document_type,
                title=title,
                content=doc_content.strip(),
                embedding=embedding_val
            )
            self.db.add(doc)
            self.db.commit()
            self.db.refresh(doc)
            return doc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

