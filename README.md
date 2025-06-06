
# HyPE: Hypothetical Prompt Embeddings for Shiny Documentation

HyPE is a novel information retrieval system designed to improve query relevance for documentation-based questions. Instead of matching queries directly to document text, HyPE generates and indexes **hypothetical questions** that each document could answer. This transforms the retrieval task into a **question-to-question matching** problem, enhancing semantic understanding and user experience. 

Original Paper link: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5139335

---

## 🧠 Key Concept

**Traditional RAG**: Query → Embed → Match to document chunks  
**HyPE**: Query → Embed → Match to hypothetical questions → Retrieve relevant document chunks

By doing the heavy lifting at indexing time, HyPE avoids runtime overhead and boosts precision.

---

## 🔧 Architecture Overview

```
Document Collection
     ↓
Hypothetical Question Generation (via GPT-3.5/4)
     ↓
Vector Embedding (OpenAI)
     ↓
FAISS Index (IndexFlatL2)
     ↓
Query Embedding → Question Matching → Document Retrieval → Answer Generation
```

---

## 📂 Project Structure

### 1. Document Storage

- Extracted from Shiny documentation using `ShinyDocCrawler`
- Stored in `JSON` format:
  - `title`, `url`, `description`
  - Main content: paragraphs, headings, lists, code examples

### 2. Hypothetical Question Storage

- Each document yields multiple **hypothetical questions**
- Questions stored with links to their source document

### 3. Embedding Storage

- Each question is embedded using **OpenAI Embeddings API**
- Embeddings saved as `.npy` files (NumPy arrays)
- Mapping maintained: `embedding → question → document`

### 4. Indexing with FAISS

- Uses **IndexFlatL2** for exact Euclidean distance
- Fast, accurate, and memory-efficient
- One-time build at indexing phase; real-time matching during queries
 
More about FAISS: https://faiss.ai/index.html

### 5. Configuration

- Model parameters, settings, and versioning are persisted for reproducibility
- Stored alongside documents and vectors

---

## 🧮 Algorithms and Tools Used

| Component                     | Tool/Algorithm                  |
|------------------------------|----------------------------------|
| Question Generation           | GPT-3.5 / GPT-4                  |
| Embedding Model               | OpenAI `text-embedding-ada-002` |
| Vector Similarity Search      | FAISS `IndexFlatL2`             |
| Document-Question Mapping     | Custom indexing schema          |
| Data Format                   | JSON, NumPy `.npy`              |

---

## 🚀 Query Workflow

1. User inputs a natural language question
2. Query is embedded using the same OpenAI model
3. Embedding is compared with stored hypothetical questions via FAISS
4. Top-matched questions → linked documents retrieved
5. Documents passed as context to LLM → Answer generated

---

## ✅ Benefits of HyPE

- Reduces semantic mismatch between query and document
- Avoids runtime prompt generation
- Precise and fast similarity search
- Transparent, reproducible storage and indexing

---

## 🧭 Optional: Crawling and Retrieval via `crawl4ai`

As an optional approach, this project also includes a fully automated documentation crawler built on top of the `crawl4ai` framework. This crawler launches parallel headless browser sessions to visit pages starting from the Shiny for Python documentation's overview. It extracts content as structured markdown while respecting a maximum recursion depth. Internal links are followed dynamically, and content from visited pages is saved into a single JSON file. The crawler is designed to handle memory adaptively and avoids redundant or external URLs to ensure efficient and focused crawling.

Once the documentation is collected, the `Shiny_crawl4ai_HyPE.ipynb` notebook can be used to load the markdown content and embed it using a language model. The embedded content is indexed into a vector database, enabling retrieval-augmented generation (RAG). This allows the system to answer user queries by retrieving the most relevant documentation chunks and combining them with a generative model for accurate and contextual responses. This method serves as a lightweight, extensible alternative to manually curated data pipelines.
