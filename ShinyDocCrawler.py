# ShinyDocCrawler.py
import requests
from bs4 import BeautifulSoup
import os
import json
import re
from urllib.parse import urljoin, urlparse
import time
from collections import deque

class ShinyDocCrawler:
    def __init__(self, base_url="https://shiny.posit.co/py/", output_dir="shiny_docs", max_depth=3):
        self.base_url = base_url
        self.output_dir = output_dir
        self.max_depth = max_depth
        self.visited = set()
        self.doc_structure = {}
        self.toc_structure = {}
        self.url_queue = deque()
        
        # Ensure output directories exist
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(f"{output_dir}/content", exist_ok=True)
    
    def clean_text(self, text):
        """Clean text content by removing extra whitespace"""
        return re.sub(r'\s+', ' ', text).strip()
    
    def extract_metadata(self, soup, url):
        """Extract metadata from the page"""
        metadata = {
            "title": soup.title.text.strip() if soup.title else "",
            "description": "",
            "url": url
        }
        
        # Extract description from meta tags
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag and desc_tag.get("content"):
            metadata["description"] = desc_tag["content"]
            
        return metadata
    
    def extract_content(self, soup):
        """Extract main content from the page"""
        content_div = soup.find('main', id='quarto-document-content')
        if not content_div:
            content_div = soup.find('div', class_='content')
        
        if content_div:
            # Extract paragraphs, headings, code blocks, etc.
            elements = []
            for element in content_div.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'pre', 'div', 'ul', 'ol', 'li']):
                if element.name in ['p', 'h1', 'h2', 'h3', 'h4', 'h5']:
                    text = self.clean_text(element.get_text())
                    if text:
                        elements.append({
                            "type": element.name,
                            "text": text
                        })
                elif element.name == 'pre':
                    code = element.get_text()
                    if code.strip():
                        elements.append({
                            "type": "code",
                            "text": code
                        })
                elif element.name in ['ul', 'ol']:
                    list_items = []
                    for li in element.find_all('li', recursive=False):
                        list_items.append(self.clean_text(li.get_text()))
                    
                    if list_items:
                        elements.append({
                            "type": element.name,
                            "items": list_items
                        })
            
            return elements
        return []
    
    def extract_code_examples(self, soup):
        """Extract code examples from the page"""
        examples = []
        for code in soup.find_all(['pre', 'div'], class_=['sourceCode', 'shinylive-python']):
            code_text = code.get_text()
            if code_text.strip():
                examples.append(code_text)
        return examples
    
    def parse_toc(self, soup, current_url):
        """Extract table of contents structure"""
        toc = []
        # Get the current directory from the URL
        current_dir = os.path.dirname(current_url)
        if not current_dir.endswith('/'):
            current_dir += '/'
            
        toc_nav = soup.find('nav', id='TOC')
        
        if toc_nav:
            for item in toc_nav.find_all('a', class_='nav-link'):
                section = {}
                section["title"] = item.text.strip()
                href = item.get('href')
                if href:
                    if not href.startswith(('http://', 'https://', '/')):
                        href = urljoin(current_dir, href)
                    section["url"] = href
                toc.append(section)
        
        # Also look for sidebar navigation
        sidebar_nav = soup.find('nav', id='quarto-sidebar')
        if sidebar_nav:
            sidebar_sections = []
            for section in sidebar_nav.find_all('li', class_='sidebar-item'):
                section_title = section.find('span', class_='menu-text')
                section_link = section.find('a', class_='sidebar-item-text')
                
                if section_title:
                    s = {"title": section_title.text.strip()}
                    if section_link and section_link.get('href'):
                        href = section_link.get('href')
                        if not href.startswith(('http://', 'https://', '/')):
                            href = urljoin(current_dir, href)
                        s["url"] = href
                    sidebar_sections.append(s)
            
            if sidebar_sections:
                toc.extend(sidebar_sections)
        
        return toc
    
    def extract_links(self, soup, current_url):
        """Extract all links from the page"""
        links = []
        # Get the current directory from the URL
        current_dir = os.path.dirname(current_url)
        if not current_dir.endswith('/'):
            current_dir += '/'
        
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            
            # Skip anchor links
            if href.startswith('#'):
                continue
            
            # Skip external links
            if href.startswith(('http://', 'https://')) and not href.startswith(self.base_url):
                continue
            
            # Make the URL absolute by combining with current directory for relative links
            if not href.startswith(('http://', 'https://', '/')):
                href = urljoin(current_dir, href)
            
            # For absolute links within the site (starting with /)
            if href.startswith('/'):
                href = urljoin(self.base_url, href.lstrip('/'))
            
            # Convert absolute URLs to relative paths
            if href.startswith(self.base_url):
                href = href[len(self.base_url):]
            
            # Only include .html pages and directories
            if href.endswith('.html') or href.endswith('/'):
                links.append(href)
        
        return links
    
    def crawl_page(self, url, parent=None, depth=0):
        """Crawl a single page and extract its content"""
        if url in self.visited or depth > self.max_depth:
            return
        
        self.visited.add(url)
        full_url = urljoin(self.base_url, url)
        
        try:
            print(f"Crawling [{depth}] {full_url}")
            
            # Add delay to be respectful
            time.sleep(1)
            
            response = requests.get(full_url)
            if response.status_code != 200:
                print(f"Error: Status code {response.status_code} for {full_url}")
                return
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Generate a unique ID for this document
            doc_id = url.replace('/', '_').replace('.', '_')
            if doc_id.endswith('_'):
                doc_id = doc_id[:-1]
            
            # Extract metadata
            metadata = self.extract_metadata(soup, url)
            
            # Extract main content
            content = self.extract_content(soup)
            
            # Extract code examples
            code_examples = self.extract_code_examples(soup)
            
            # Parse TOC if this is an index page
            toc = self.parse_toc(soup, url)
            if toc:
                self.toc_structure[doc_id] = toc
            
            # Create document record
            self.doc_structure[doc_id] = {
                "url": url,
                "title": metadata["title"],
                "description": metadata["description"],
                "parent": parent,
                "children": [],
                "code_examples_count": len(code_examples),
                "content_length": len(content)
            }
            
            # Save the content to a file
            page_data = {
                "metadata": metadata,
                "content": content,
                "code_examples": code_examples,
                "toc": toc
            }
            
            with open(f"{self.output_dir}/content/{doc_id}.json", 'w', encoding='utf-8') as f:
                json.dump(page_data, f, ensure_ascii=False, indent=2)
            
            # Extract links for next pages to crawl
            links = self.extract_links(soup, url)
            
            # Add extracted links to the queue and document structure
            for link in links:
                link_id = link.replace('/', '_').replace('.', '_')
                if link_id.endswith('_'):
                    link_id = link_id[:-1]
                
                if parent:
                    if link_id not in self.doc_structure.get(parent, {}).get("children", []):
                        self.doc_structure[parent]["children"].append(link_id)
                
                if link not in self.visited:
                    self.url_queue.append((link, doc_id, depth + 1))
            
        except Exception as e:
            print(f"Error crawling {url}: {e}")
    
    def start_crawling(self, entry_point="docs/overview.html"):
        """Start the crawling process using BFS"""
        # Add entry point to the queue
        self.url_queue.append((entry_point, None, 0))
        
        # Process the queue
        while self.url_queue:
            url, parent, depth = self.url_queue.popleft()
            self.crawl_page(url, parent, depth)
        
        # Save the document structure
        with open(f"{self.output_dir}/doc_structure.json", 'w', encoding='utf-8') as f:
            json.dump(self.doc_structure, f, ensure_ascii=False, indent=2)
        
        # Save the TOC structure
        with open(f"{self.output_dir}/toc_structure.json", 'w', encoding='utf-8') as f:
            json.dump(self.toc_structure, f, ensure_ascii=False, indent=2)
            
        print(f"Crawling completed. Visited {len(self.visited)} pages.")