# GitHubRepoCrawler.py
import requests
from bs4 import BeautifulSoup
import os
import json
import re
from urllib.parse import urljoin, urlparse
import time
from collections import deque
import base64

class GitHubRepoCrawler:
    def __init__(self, repo_url="https://github.com/vnijs/pyrsm/tree/main", output_dir="pyrsm_docs", max_depth=5):
        # Parse the GitHub URL to extract owner and repo
        self.repo_url = repo_url
        self.output_dir = output_dir
        self.max_depth = max_depth
        self.visited = set()
        self.doc_structure = {}
        self.toc_structure = {}
        self.url_queue = deque()
        
        # Extract repo info from URL
        url_parts = repo_url.replace('https://github.com/', '').split('/')
        self.owner = url_parts[0]
        self.repo = url_parts[1]
        self.branch = url_parts[3] if len(url_parts) > 3 else 'main'
        
        # GitHub API base URL
        self.api_base = f"https://api.github.com/repos/{self.owner}/{self.repo}"
        
        # Ensure output directories exist
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(f"{output_dir}/content", exist_ok=True)
        
        # Add some headers to avoid rate limiting
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/vnd.github.v3+json'
        }
    
    def clean_text(self, text):
        """Clean text content by removing extra whitespace"""
        return re.sub(r'\s+', ' ', text).strip()
    
    def get_file_content_from_api(self, file_path):
        """Get file content using GitHub API"""
        try:
            api_url = f"{self.api_base}/contents/{file_path}?ref={self.branch}"
            response = requests.get(api_url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('content'):
                    # Decode base64 content
                    content = base64.b64decode(data['content']).decode('utf-8')
                    return content, data
                return None, data
            return None, None
        except Exception as e:
            print(f"Error fetching {file_path} from API: {e}")
            return None, None
    
    def get_directory_contents(self, dir_path=""):
        """Get directory contents using GitHub API"""
        try:
            api_url = f"{self.api_base}/contents/{dir_path}?ref={self.branch}"
            response = requests.get(api_url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Error fetching directory {dir_path}: {e}")
            return []
    
    def extract_metadata_from_file(self, content, file_info):
        """Extract metadata from file content and GitHub info"""
        metadata = {
            "name": file_info.get('name', ''),
            "path": file_info.get('path', ''),
            "type": file_info.get('type', 'file'),
            "size": file_info.get('size', 0),
            "sha": file_info.get('sha', ''),
            "url": file_info.get('html_url', ''),
            "download_url": file_info.get('download_url', ''),
            "description": ""
        }
        
        # For markdown files, try to extract title from first heading
        if file_info.get('name', '').endswith('.md') and content:
            lines = content.split('\n')
            for line in lines:
                if line.startswith('# '):
                    metadata["title"] = line[2:].strip()
                    break
                elif line.startswith('## '):
                    metadata["title"] = line[3:].strip()
                    break
            
            # Try to extract description from first paragraph
            in_code_block = False
            for line in lines:
                line = line.strip()
                if line.startswith('```'):
                    in_code_block = not in_code_block
                    continue
                if not in_code_block and line and not line.startswith('#') and not line.startswith('```'):
                    if len(line) > 20:  # Reasonable description length
                        metadata["description"] = line[:200]  # Limit description length
                        break
        
        return metadata
    
    def parse_markdown_content(self, content):
        """Parse markdown content into structured elements"""
        if not content:
            return []
        
        elements = []
        lines = content.split('\n')
        current_element = None
        in_code_block = False
        code_language = ""
        code_content = []
        
        for line in lines:
            stripped = line.strip()
            
            # Handle code blocks
            if stripped.startswith('```'):
                if not in_code_block:
                    # Starting code block
                    in_code_block = True
                    code_language = stripped[3:].strip()
                    code_content = []
                else:
                    # Ending code block
                    in_code_block = False
                    if code_content:
                        elements.append({
                            "type": "code",
                            "language": code_language,
                            "text": '\n'.join(code_content)
                        })
                    code_content = []
                    code_language = ""
                continue
            
            if in_code_block:
                code_content.append(line)
                continue
            
            # Handle headings
            if stripped.startswith('#'):
                level = len(stripped) - len(stripped.lstrip('#'))
                text = stripped[level:].strip()
                if text:
                    elements.append({
                        "type": f"h{level}",
                        "text": text
                    })
            
            # Handle lists
            elif stripped.startswith(('- ', '* ', '+ ')) or re.match(r'^\d+\.', stripped):
                list_item = stripped[2:].strip() if stripped.startswith(('- ', '* ', '+ ')) else re.sub(r'^\d+\.\s*', '', stripped)
                if list_item:
                    # Check if we're continuing a list
                    if current_element and current_element["type"] in ["ul", "ol"]:
                        current_element["items"].append(list_item)
                    else:
                        # Start new list
                        list_type = "ol" if re.match(r'^\d+\.', stripped) else "ul"
                        current_element = {
                            "type": list_type,
                            "items": [list_item]
                        }
                        elements.append(current_element)
            
            # Handle regular paragraphs
            elif stripped and not stripped.startswith('>'):  # Exclude blockquotes for now
                if current_element and current_element["type"] == "p":
                    current_element["text"] += " " + stripped
                else:
                    current_element = {
                        "type": "p",
                        "text": stripped
                    }
                    elements.append(current_element)
            else:
                current_element = None
        
        return elements
    
    def parse_python_content(self, content):
        """Parse Python file content"""
        if not content:
            return []
        
        elements = []
        lines = content.split('\n')
        
        # Extract docstring if present
        in_docstring = False
        docstring_lines = []
        docstring_quotes = None
        
        # Extract classes and functions
        current_function = None
        current_class = None
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Handle docstrings
            if not in_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
                in_docstring = True
                docstring_quotes = stripped[:3]
                docstring_content = stripped[3:]
                if docstring_content.endswith(docstring_quotes):
                    # Single-line docstring
                    elements.append({
                        "type": "docstring",
                        "text": docstring_content[:-3].strip()
                    })
                    in_docstring = False
                else:
                    docstring_lines = [docstring_content] if docstring_content else []
                continue
            
            if in_docstring:
                if stripped.endswith(docstring_quotes):
                    docstring_lines.append(stripped[:-3])
                    elements.append({
                        "type": "docstring",
                        "text": '\n'.join(docstring_lines).strip()
                    })
                    in_docstring = False
                    docstring_lines = []
                else:
                    docstring_lines.append(line)
                continue
            
            # Handle class definitions
            if stripped.startswith('class '):
                class_match = re.match(r'class\s+(\w+).*:', stripped)
                if class_match:
                    elements.append({
                        "type": "class",
                        "name": class_match.group(1),
                        "text": stripped
                    })
            
            # Handle function definitions
            elif stripped.startswith('def '):
                func_match = re.match(r'def\s+(\w+)\s*\(.*\).*:', stripped)
                if func_match:
                    elements.append({
                        "type": "function",
                        "name": func_match.group(1),
                        "text": stripped
                    })
            
            # Handle imports
            elif stripped.startswith(('import ', 'from ')):
                elements.append({
                    "type": "import",
                    "text": stripped
                })
        
        return elements
    
    def extract_content_from_file(self, content, file_info):
        """Extract structured content based on file type"""
        file_name = file_info.get('name', '')
        
        if file_name.endswith('.md'):
            return self.parse_markdown_content(content)
        elif file_name.endswith('.py'):
            return self.parse_python_content(content)
        elif file_name.endswith(('.txt', '.rst')):
            # Simple text content
            if content:
                return [{
                    "type": "text",
                    "text": content
                }]
        elif file_name.endswith(('.json', '.yml', '.yaml', '.toml')):
            # Configuration files
            return [{
                "type": "config",
                "text": content if content else ""
            }]
        
        return []
    
    def extract_code_examples(self, content, file_info):
        """Extract code examples from the content"""
        examples = []
        file_name = file_info.get('name', '')
        
        if file_name.endswith('.py'):
            # For Python files, the entire content is a code example
            if content:
                examples.append(content)
        elif file_name.endswith('.md') and content:
            # Extract code blocks from markdown
            lines = content.split('\n')
            in_code_block = False
            current_code = []
            
            for line in lines:
                if line.strip().startswith('```'):
                    if in_code_block:
                        if current_code:
                            examples.append('\n'.join(current_code))
                        current_code = []
                        in_code_block = False
                    else:
                        in_code_block = True
                elif in_code_block:
                    current_code.append(line)
        
        return examples
    
    def crawl_directory(self, dir_path="", parent=None, depth=0):
        """Crawl a directory and its contents"""
        if depth > self.max_depth:
            return
        
        print(f"Crawling directory [{depth}]: {dir_path or 'root'}")
        
        # Add delay to be respectful to GitHub API
        time.sleep(0.5)
        
        contents = self.get_directory_contents(dir_path)
        
        for item in contents:
            item_path = item.get('path', '')
            item_name = item.get('name', '')
            item_type = item.get('type', '')
            
            # Skip hidden files and common non-documentation directories
            if item_name.startswith('.') or item_name in ['__pycache__', 'node_modules', '.git']:
                continue
            
            # Generate a unique ID for this item
            doc_id = item_path.replace('/', '_').replace('.', '_')
            
            if item_type == 'dir':
                # Create directory entry
                self.doc_structure[doc_id] = {
                    "path": item_path,
                    "name": item_name,
                    "type": "directory",
                    "parent": parent,
                    "children": [],
                    "url": item.get('html_url', ''),
                    "content_length": 0
                }
                
                # Add to parent's children
                if parent and parent in self.doc_structure:
                    self.doc_structure[parent]["children"].append(doc_id)
                
                # Recursively crawl subdirectory
                self.crawl_directory(item_path, doc_id, depth + 1)
                
            elif item_type == 'file':
                # Only process certain file types
                if not item_name.endswith(('.md', '.py', '.txt', '.rst', '.json', '.yml', '.yaml', '.toml', '.cfg')):
                    continue
                
                if item_path in self.visited:
                    continue
                
                self.visited.add(item_path)
                
                # Get file content
                content, file_info = self.get_file_content_from_api(item_path)
                
                # Extract metadata
                metadata = self.extract_metadata_from_file(content, item)
                
                # Extract structured content
                structured_content = self.extract_content_from_file(content, item)
                
                # Extract code examples
                code_examples = self.extract_code_examples(content, item)
                
                # Create document record
                self.doc_structure[doc_id] = {
                    "path": item_path,
                    "name": item_name,
                    "type": "file",
                    "file_type": item_name.split('.')[-1] if '.' in item_name else 'unknown',
                    "title": metadata.get("title", item_name),
                    "description": metadata.get("description", ""),
                    "parent": parent,
                    "children": [],
                    "url": item.get('html_url', ''),
                    "size": item.get('size', 0),
                    "code_examples_count": len(code_examples),
                    "content_length": len(structured_content)
                }
                
                # Add to parent's children
                if parent and parent in self.doc_structure:
                    self.doc_structure[parent]["children"].append(doc_id)
                
                # Save the content to a file
                page_data = {
                    "metadata": metadata,
                    "content": structured_content,
                    "code_examples": code_examples,
                    "raw_content": content
                }
                
                with open(f"{self.output_dir}/content/{doc_id}.json", 'w', encoding='utf-8') as f:
                    json.dump(page_data, f, ensure_ascii=False, indent=2)
                
                print(f"  Processed file: {item_name}")
    
    def build_toc_structure(self):
        """Build table of contents structure from the crawled documents"""
        toc = {}
        
        # Find README files to use as entry points
        readme_files = []
        for doc_id, doc_info in self.doc_structure.items():
            if doc_info.get('type') == 'file' and doc_info.get('name', '').lower().startswith('readme'):
                readme_files.append((doc_id, doc_info))
        
        # Build hierarchical TOC
        def build_toc_recursive(parent_id=None, level=0):
            toc_items = []
            for doc_id, doc_info in self.doc_structure.items():
                if doc_info.get('parent') == parent_id:
                    item = {
                        "title": doc_info.get('title', doc_info.get('name', '')),
                        "path": doc_info.get('path', ''),
                        "type": doc_info.get('type', ''),
                        "url": doc_info.get('url', ''),
                        "children": build_toc_recursive(doc_id, level + 1) if doc_info.get('children') else []
                    }
                    toc_items.append(item)
            return toc_items
        
        toc['structure'] = build_toc_recursive()
        toc['readme_files'] = [(doc_id, info['title']) for doc_id, info in readme_files]
        
        return toc
    
    def start_crawling(self):
        """Start the crawling process"""
        print(f"Starting to crawl {self.repo_url}")
        print(f"Repository: {self.owner}/{self.repo}")
        print(f"Branch: {self.branch}")
        
        # Start crawling from the root directory
        self.crawl_directory()
        
        # Build TOC structure
        self.toc_structure = self.build_toc_structure()
        
        # Save the document structure
        with open(f"{self.output_dir}/doc_structure.json", 'w', encoding='utf-8') as f:
            json.dump(self.doc_structure, f, ensure_ascii=False, indent=2)
        
        # Save the TOC structure
        with open(f"{self.output_dir}/toc_structure.json", 'w', encoding='utf-8') as f:
            json.dump(self.toc_structure, f, ensure_ascii=False, indent=2)
        
        print(f"Crawling completed. Processed {len(self.visited)} files.")
        print(f"Total items in structure: {len(self.doc_structure)}")

# Usage example
if __name__ == "__main__":
    crawler = GitHubRepoCrawler(
        repo_url="https://github.com/vnijs/pyrsm/tree/main",
        output_dir="pyrsm_docs",
        max_depth=3
    )
    crawler.start_crawling()