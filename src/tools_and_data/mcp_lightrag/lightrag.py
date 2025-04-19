"""
Simple implementation of LightRAG class for local document retrieval
"""
import os
import json
from typing import List, Dict, Any, Optional
import hashlib

class LightRAG:
    """A lightweight RAG (Retrieval Augmented Generation) implementation for local files."""
    
    def __init__(self, name: str):
        """Initialize a new LightRAG instance.
        
        Args:
            name: Name of the index
        """
        self.name = name
        self.documents = []
        self.index = {}
    
    def index_local_files(self, directory: str, file_extensions: List[str] = [".md"]) -> None:
        """Index local files from a directory.
        
        Args:
            directory: Directory path to index files from
            file_extensions: List of file extensions to include
        """
        self.documents = []
        for root, _, files in os.walk(directory):
            for file in files:
                if any(file.endswith(ext) for ext in file_extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            doc_id = hashlib.md5(file_path.encode()).hexdigest()
                            self.documents.append({
                                "id": doc_id,
                                "path": file_path,
                                "content": content,
                                "title": os.path.basename(file_path)
                            })
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")
        
        # Create a simple keyword index
        self._build_index()
    
    def _build_index(self) -> None:
        """Build a simple keyword-based index."""
        self.index = {}
        for doc in self.documents:
            content = doc["content"].lower()
            words = set(content.split())
            for word in words:
                if word not in self.index:
                    self.index[word] = []
                self.index[word].append(doc["id"])
    
    def save_index(self, filename: str) -> None:
        """Save the index to a file.
        
        Args:
            filename: Name of the file to save the index to
        """
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                "name": self.name,
                "documents": self.documents,
                "index": self.index
            }, f)
    
    def load_index(self, filename: str) -> None:
        """Load an index from a file.
        
        Args:
            filename: Name of the file to load the index from
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.name = data.get("name", self.name)
                self.documents = data.get("documents", [])
                self.index = data.get("index", {})
        except FileNotFoundError:
            print(f"Index file {filename} not found. Creating a new index.")
    
    def query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Query the index for relevant documents.
        
        Args:
            query: Query string
            top_k: Number of top results to return
            
        Returns:
            List of document dictionaries
        """
        query_words = query.lower().split()
        doc_scores = {}
        
        for word in query_words:
            if word in self.index:
                for doc_id in self.index[word]:
                    if doc_id not in doc_scores:
                        doc_scores[doc_id] = 0
                    doc_scores[doc_id] += 1
        
        # Sort by score
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Get top-k documents
        results = []
        for doc_id, _ in sorted_docs[:top_k]:
            for doc in self.documents:
                if doc["id"] == doc_id:
                    results.append(doc)
                    break
        
        return results
