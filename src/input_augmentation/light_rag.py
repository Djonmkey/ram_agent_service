import sys 
import asyncio
import tiktoken

from typing import Dict, Any, List
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_complete, openai_embed
from lightrag.kg.shared_storage import initialize_pipeline_status

from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: discord -> output_actions -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_input_augmentation_config

WORKING_DIR = Path("rag_storage")       # persists vectors, graph, cache
CONTENT_PATH = Path("rag_content.txt")  # UTF‑8 text file
CHUNK_TOKENS = 800                      # customise if desired
OVERLAP_TOKENS = 80

def _read_content() -> str:
    """Read and return the entire book as one UTF‑8 string."""
    return CONTENT_PATH.read_text(encoding="utf‑8")

def _simple_semantic_split(text: str,
                           chunk_tokens: int = CHUNK_TOKENS,
                           overlap: int = OVERLAP_TOKENS) -> List[str]:
    """
    Split *text* on blank lines but enforce a soft token cap with overlap.

    This keeps paragraphs together while honouring the token window.
    """
    enc = tiktoken.get_encoding("cl100k_base")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    buf: List[str] = []

    for para in paragraphs:
        tentative = "\n\n".join(buf + [para])
        if len(enc.encode(tentative)) <= chunk_tokens:
            buf.append(para)
        else:
            # flush current buffer
            if buf:
                chunks.append("\n\n".join(buf))
            # start new buffer; could itself be larger than limit
            buf = [para]

    if buf:
        chunks.append("\n\n".join(buf))

    # add overlap
    final_chunks: List[str] = []
    for idx, chunk in enumerate(chunks):
        prev_tail = chunks[idx - 1] if idx > 0 else ""
        if prev_tail:
            tail_tokens = enc.encode(prev_tail)[-overlap:]
            chunk_tokens_list = enc.encode(chunk)
            merged = enc.decode(tail_tokens + chunk_tokens_list)
            final_chunks.append(merged)
        else:
            final_chunks.append(chunk)

    return final_chunks

async def _build_rag() -> LightRAG:
    """
    Initialise LightRAG with OpenAI functions and ingest the book.
    """
    rag = LightRAG(
        working_dir=str(WORKING_DIR),
        embedding_func=openai_embed,          # text‑embedding‑3‑small by default
        llm_model_func=gpt_4o_complete,
        chunk_token_size=CHUNK_TOKENS,
        chunk_overlap_token_size=OVERLAP_TOKENS,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()

    # Ingest
    if not rag.has_content():                # skip if already indexed
        for chunk in _simple_semantic_split(_read_content()):
            rag.insert(chunk)

    return rag

async def ask(question: str, mode, top_k, response_type) -> str:
    """
    Ask *question* against the RAG index and return the gpt‑4o answer.
    """
    rag = await _build_rag()
    answer = await rag.query(
        question,
        param=QueryParam(
            mode=mode,                      # vector + graph hybrid retrieval
            top_k=top_k,                    # fine‑tune as needed
            response_type=response_type
        ),
    )
    await rag.finalize_storages()
    return answer

def augment_prompt(agent_name: str, prompt: str, meta_data: Dict[str, Any]) -> str:
    """
    Augment the prompt using RAG. This is a blocking call that will
    wait for the async RAG query to complete before returning.
    
    Args:
        agent_name: The name of the agent
        prompt: The prompt to augment
        meta_data: Additional metadata
        
    Returns:
        The augmented prompt
    """
    input_augmentation_config = get_input_augmentation_config(agent_name)

    # Update configuration from agent settings
    global WORKING_DIR, CHUNK_TOKENS, OVERLAP_TOKENS, CONTENT_PATH
    WORKING_DIR = Path(input_augmentation_config.get("working_dir", "rag_storage"))
    CHUNK_TOKENS = input_augmentation_config.get("chunk_tokens", 800)
    OVERLAP_TOKENS = input_augmentation_config.get("overlap_tokens", 80)
    content_path = input_augmentation_config.get("content_path", "rag_content.txt")
    if content_path:
        CONTENT_PATH = Path(content_path)

    mode = input_augmentation_config.get("mode", "mix")
    top_k = input_augmentation_config.get("top_k", 8)
    response_type = input_augmentation_config.get("response_type", "Multiple Paragraphs")

    # Block until the async operation completes
    result = asyncio.run(ask(prompt, mode, top_k, response_type))
    
    return result
