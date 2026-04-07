from dataclasses import dataclass, field


@dataclass
class RepoRecord:
    repo_name: str        # "owner/repo"
    owner: str
    readme_text: str = ""
    file_contents: dict = field(default_factory=dict)  # {filename: content}
    commit_sha: str = ""


@dataclass
class Chunk:
    id: str               # "{repo_name}::{file_path}::{index}"
    repo_name: str
    file_path: str
    chunk_type: str       # "readme" | "code"
    section_header: str = ""
    function_name: str = ""
    content: str = ""
    token_count: int = 0


@dataclass
class QueryPlan:
    intent: str           # "find_tool" | "compare_tools" | "explain_tool" | "discuss_results" | "followup_tool" | "general_chat"
    domain: str = ""
    keywords: list = field(default_factory=list)
    preferred_collections: list = field(default_factory=lambda: ["tool_profiles", "readme_chunks", "code_chunks"])
    filters: dict = field(default_factory=dict)
    referenced_tools: list = field(default_factory=list)


@dataclass
class RankedResult:
    repo_name: str
    chunk_text: str
    score: float
    source_collection: str
    reason: str = ""
