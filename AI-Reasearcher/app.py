from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import json
import sqlite3
from datetime import datetime
import PyPDF2
from anthropic import Anthropic

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
DATABASE = 'research_hub.db'
ALLOWED_EXTENSIONS = {'pdf', 'txt'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Anthropic client (set your API key as environment variable)
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def init_db():
    """Initialize the SQLite database"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Documents table
    c.execute('''CREATE TABLE IF NOT EXISTS documents
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  filename TEXT NOT NULL,
                  file_path TEXT NOT NULL,
                  content TEXT,
                  summary TEXT,
                  topic TEXT,
                  upload_date TEXT NOT NULL,
                  file_type TEXT)''')
    
    # Keywords table
    c.execute('''CREATE TABLE IF NOT EXISTS keywords
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  doc_id INTEGER,
                  keyword TEXT,
                  FOREIGN KEY (doc_id) REFERENCES documents (id))''')
    
    # Entities table
    c.execute('''CREATE TABLE IF NOT EXISTS entities
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  doc_id INTEGER,
                  entity TEXT,
                  FOREIGN KEY (doc_id) REFERENCES documents (id))''')
    
    # Tags table
    c.execute('''CREATE TABLE IF NOT EXISTS tags
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  doc_id INTEGER,
                  tag TEXT,
                  FOREIGN KEY (doc_id) REFERENCES documents (id))''')
    
    # Notes table
    c.execute('''CREATE TABLE IF NOT EXISTS notes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  doc_id INTEGER,
                  note_text TEXT,
                  timestamp TEXT,
                  FOREIGN KEY (doc_id) REFERENCES documents (id))''')
    
    # Links table (for document relationships)
    c.execute('''CREATE TABLE IF NOT EXISTS document_links
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  doc_id INTEGER,
                  linked_doc_id INTEGER,
                  FOREIGN KEY (doc_id) REFERENCES documents (id),
                  FOREIGN KEY (linked_doc_id) REFERENCES documents (id))''')
    
    conn.commit()
    conn.close()

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    """Extract text content from PDF file"""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            return text
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return None

def extract_text_from_txt(file_path):
    """Extract text content from text file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error reading text file: {e}")
        return None

def analyze_document_with_ai(text, title):
    """Use Claude API to analyze document"""
    try:
        # Truncate text if too long
        text_sample = text[:5000] if len(text) > 5000 else text
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this research document titled "{title}".

Text: {text_sample}

Provide a JSON response with:
{{
  "summary": "2-3 sentence summary",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "entities": ["entity1", "entity2", "entity3"],
  "topic": "main topic category"
}}

Respond ONLY with valid JSON, no other text."""
                }
            ]
        )
        
        # Extract text from response
        response_text = message.content[0].text
        # Remove markdown code blocks if present
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        return json.loads(response_text)
    except Exception as e:
        print(f"Error analyzing document: {e}")
        return {
            "summary": "Analysis unavailable",
            "keywords": [],
            "entities": [],
            "topic": "General"
        }

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload and process document"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        unique_filename = timestamp + filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        file.save(file_path)
        
        # Extract text based on file type
        file_ext = filename.rsplit('.', 1)[1].lower()
        if file_ext == 'pdf':
            text_content = extract_text_from_pdf(file_path)
        else:
            text_content = extract_text_from_txt(file_path)
        
        if not text_content:
            return jsonify({'error': 'Could not extract text from file'}), 500
        
        # Analyze document with AI
        title = filename.rsplit('.', 1)[0]
        analysis = analyze_document_with_ai(text_content, title)
        
        # Store in database
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        c.execute('''INSERT INTO documents 
                     (title, filename, file_path, content, summary, topic, upload_date, file_type)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (title, unique_filename, file_path, text_content, 
                   analysis['summary'], analysis['topic'], 
                   datetime.now().isoformat(), file_ext))
        
        doc_id = c.lastrowid
        
        # Store keywords
        for keyword in analysis['keywords']:
            c.execute('INSERT INTO keywords (doc_id, keyword) VALUES (?, ?)', (doc_id, keyword))
        
        # Store entities
        for entity in analysis['entities']:
            c.execute('INSERT INTO entities (doc_id, entity) VALUES (?, ?)', (doc_id, entity))
        
        # Store topic as initial tag
        c.execute('INSERT INTO tags (doc_id, tag) VALUES (?, ?)', (doc_id, analysis['topic']))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'File uploaded successfully',
            'doc_id': doc_id,
            'analysis': analysis
        }), 201
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/documents', methods=['GET'])
def get_documents():
    """Get all documents with their metadata"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('SELECT * FROM documents ORDER BY upload_date DESC')
    docs = c.fetchall()
    
    documents = []
    for doc in docs:
        doc_dict = dict(doc)
        doc_id = doc['id']
        
        # Get keywords
        c.execute('SELECT keyword FROM keywords WHERE doc_id = ?', (doc_id,))
        doc_dict['keywords'] = [row['keyword'] for row in c.fetchall()]
        
        # Get entities
        c.execute('SELECT entity FROM entities WHERE doc_id = ?', (doc_id,))
        doc_dict['entities'] = [row['entity'] for row in c.fetchall()]
        
        # Get tags
        c.execute('SELECT tag FROM tags WHERE doc_id = ?', (doc_id,))
        doc_dict['tags'] = [row['tag'] for row in c.fetchall()]
        
        # Don't send full content in list view
        doc_dict.pop('content', None)
        
        documents.append(doc_dict)
    
    conn.close()
    return jsonify(documents)

@app.route('/api/documents/<int:doc_id>', methods=['GET'])
def get_document(doc_id):
    """Get a specific document with full content"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('SELECT * FROM documents WHERE id = ?', (doc_id,))
    doc = c.fetchone()
    
    if not doc:
        conn.close()
        return jsonify({'error': 'Document not found'}), 404
    
    doc_dict = dict(doc)
    
    # Get keywords
    c.execute('SELECT keyword FROM keywords WHERE doc_id = ?', (doc_id,))
    doc_dict['keywords'] = [row['keyword'] for row in c.fetchall()]
    
    # Get entities
    c.execute('SELECT entity FROM entities WHERE doc_id = ?', (doc_id,))
    doc_dict['entities'] = [row['entity'] for row in c.fetchall()]
    
    # Get tags
    c.execute('SELECT tag FROM tags WHERE doc_id = ?', (doc_id,))
    doc_dict['tags'] = [row['tag'] for row in c.fetchall()]
    
    # Get notes
    c.execute('SELECT * FROM notes WHERE doc_id = ? ORDER BY timestamp DESC', (doc_id,))
    doc_dict['notes'] = [dict(row) for row in c.fetchall()]
    
    # Get linked documents
    c.execute('SELECT linked_doc_id FROM document_links WHERE doc_id = ?', (doc_id,))
    doc_dict['linked_docs'] = [row['linked_doc_id'] for row in c.fetchall()]
    
    conn.close()
    return jsonify(doc_dict)

@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """Delete a document and its file"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Get file path
    c.execute('SELECT file_path FROM documents WHERE id = ?', (doc_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': 'Document not found'}), 404
    
    file_path = result[0]
    
    # Delete file
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # Delete from database
    c.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
    c.execute('DELETE FROM keywords WHERE doc_id = ?', (doc_id,))
    c.execute('DELETE FROM entities WHERE doc_id = ?', (doc_id,))
    c.execute('DELETE FROM tags WHERE doc_id = ?', (doc_id,))
    c.execute('DELETE FROM notes WHERE doc_id = ?', (doc_id,))
    c.execute('DELETE FROM document_links WHERE doc_id = ? OR linked_doc_id = ?', (doc_id, doc_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Document deleted successfully'})

@app.route('/api/documents/<int:doc_id>/regenerate', methods=['POST'])
def regenerate_analysis(doc_id):
    """Regenerate AI analysis for a document"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('SELECT title, content FROM documents WHERE id = ?', (doc_id,))
    doc = c.fetchone()
    
    if not doc:
        conn.close()
        return jsonify({'error': 'Document not found'}), 404
    
    # Analyze with AI
    analysis = analyze_document_with_ai(doc['content'], doc['title'])
    
    # Update document
    c.execute('UPDATE documents SET summary = ?, topic = ? WHERE id = ?',
              (analysis['summary'], analysis['topic'], doc_id))
    
    # Clear and update keywords
    c.execute('DELETE FROM keywords WHERE doc_id = ?', (doc_id,))
    for keyword in analysis['keywords']:
        c.execute('INSERT INTO keywords (doc_id, keyword) VALUES (?, ?)', (doc_id, keyword))
    
    # Clear and update entities
    c.execute('DELETE FROM entities WHERE doc_id = ?', (doc_id,))
    for entity in analysis['entities']:
        c.execute('INSERT INTO entities (doc_id, entity) VALUES (?, ?)', (doc_id, entity))
    
    conn.commit()
    conn.close()
    
    return jsonify(analysis)

@app.route('/api/documents/<int:doc_id>/notes', methods=['POST'])
def add_note(doc_id):
    """Add a note to a document"""
    data = request.get_json()
    note_text = data.get('note')
    
    if not note_text:
        return jsonify({'error': 'Note text required'}), 400
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('INSERT INTO notes (doc_id, note_text, timestamp) VALUES (?, ?, ?)',
              (doc_id, note_text, datetime.now().isoformat()))
    
    note_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'id': note_id, 'message': 'Note added successfully'}), 201

@app.route('/api/documents/<int:doc_id>/tags', methods=['POST'])
def add_tag(doc_id):
    """Add a tag to a document"""
    data = request.get_json()
    tag = data.get('tag')
    
    if not tag:
        return jsonify({'error': 'Tag required'}), 400
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Check if tag already exists
    c.execute('SELECT id FROM tags WHERE doc_id = ? AND tag = ?', (doc_id, tag))
    if c.fetchone():
        conn.close()
        return jsonify({'message': 'Tag already exists'}), 200
    
    c.execute('INSERT INTO tags (doc_id, tag) VALUES (?, ?)', (doc_id, tag))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Tag added successfully'}), 201

@app.route('/api/documents/<int:doc_id>/links', methods=['POST'])
def link_documents(doc_id):
    """Link two documents together"""
    data = request.get_json()
    linked_doc_id = data.get('linked_doc_id')
    
    if not linked_doc_id:
        return jsonify({'error': 'Linked document ID required'}), 400
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Check if link already exists
    c.execute('SELECT id FROM document_links WHERE doc_id = ? AND linked_doc_id = ?',
              (doc_id, linked_doc_id))
    if c.fetchone():
        conn.close()
        return jsonify({'message': 'Link already exists'}), 200
    
    c.execute('INSERT INTO document_links (doc_id, linked_doc_id) VALUES (?, ?)',
              (doc_id, linked_doc_id))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Documents linked successfully'}), 201

@app.route('/api/search', methods=['GET'])
def search_documents():
    """Search documents by keyword, title, or tag"""
    query = request.args.get('q', '').lower()
    tag_filter = request.args.get('tag', '')
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if tag_filter:
        c.execute('''SELECT DISTINCT d.* FROM documents d
                     JOIN tags t ON d.id = t.doc_id
                     WHERE t.tag = ?
                     ORDER BY d.upload_date DESC''', (tag_filter,))
    elif query:
        c.execute('''SELECT DISTINCT d.* FROM documents d
                     LEFT JOIN keywords k ON d.id = k.doc_id
                     LEFT JOIN tags t ON d.id = t.doc_id
                     WHERE LOWER(d.title) LIKE ? 
                     OR LOWER(d.summary) LIKE ?
                     OR LOWER(k.keyword) LIKE ?
                     OR LOWER(t.tag) LIKE ?
                     ORDER BY d.upload_date DESC''',
                  (f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%'))
    else:
        c.execute('SELECT * FROM documents ORDER BY upload_date DESC')
    
    docs = c.fetchall()
    
    documents = []
    for doc in docs:
        doc_dict = dict(doc)
        doc_id = doc['id']
        
        c.execute('SELECT keyword FROM keywords WHERE doc_id = ?', (doc_id,))
        doc_dict['keywords'] = [row['keyword'] for row in c.fetchall()]
        
        c.execute('SELECT entity FROM entities WHERE doc_id = ?', (doc_id,))
        doc_dict['entities'] = [row['entity'] for row in c.fetchall()]
        
        c.execute('SELECT tag FROM tags WHERE doc_id = ?', (doc_id,))
        doc_dict['tags'] = [row['tag'] for row in c.fetchall()]
        
        doc_dict.pop('content', None)
        documents.append(doc_dict)
    
    conn.close()
    return jsonify(documents)

@app.route('/api/tags', methods=['GET'])
def get_all_tags():
    """Get all unique tags"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('SELECT DISTINCT tag FROM tags ORDER BY tag')
    tags = [row[0] for row in c.fetchall()]
    
    conn.close()
    return jsonify(tags)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)