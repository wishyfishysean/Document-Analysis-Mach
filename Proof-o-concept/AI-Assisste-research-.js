import React, { useState, useEffect } from 'react';
import { FileText, Upload, Search, Tag, Link, MessageSquare, Trash2, RefreshCw, BookOpen, Filter, X } from 'lucide-react';

const ResearchHub = () => {
  const [documents, setDocuments] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [notes, setNotes] = useState({});
  const [links, setLinks] = useState({});

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const docsData = await window.storage.list('doc:');
      const notesData = await window.storage.list('notes:');
      const linksData = await window.storage.list('links:');
      
      const loadedDocs = [];
      if (docsData?.keys) {
        for (const key of docsData.keys) {
          try {
            const result = await window.storage.get(key);
            if (result?.value) {
              loadedDocs.push(JSON.parse(result.value));
            }
          } catch (e) {
            console.log('Skipping key:', key);
          }
        }
      }
      
      const loadedNotes = {};
      if (notesData?.keys) {
        for (const key of notesData.keys) {
          try {
            const result = await window.storage.get(key);
            if (result?.value) {
              const docId = key.replace('notes:', '');
              loadedNotes[docId] = JSON.parse(result.value);
            }
          } catch (e) {
            console.log('Skipping notes key:', key);
          }
        }
      }
      
      const loadedLinks = {};
      if (linksData?.keys) {
        for (const key of linksData.keys) {
          try {
            const result = await window.storage.get(key);
            if (result?.value) {
              const docId = key.replace('links:', '');
              loadedLinks[docId] = JSON.parse(result.value);
            }
          } catch (e) {
            console.log('Skipping links key:', key);
          }
        }
      }
      
      setDocuments(loadedDocs);
      setNotes(loadedNotes);
      setLinks(loadedLinks);
    } catch (error) {
      console.log('No existing data, starting fresh');
    }
  };

  const analyzeDocument = async (text, title) => {
    try {
      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 1000,
          messages: [
            {
              role: "user",
              content: `Analyze this research document titled "${title}".

Text: ${text.slice(0, 5000)}

Provide a JSON response with:
{
  "summary": "2-3 sentence summary",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "entities": ["entity1", "entity2", "entity3"],
  "topic": "main topic category"
}

Respond ONLY with valid JSON, no other text.`
            }
          ],
        })
      });

      const data = await response.json();
      const text_content = data.content.map(item => item.type === "text" ? item.text : "").join("");
      const clean = text_content.replace(/```json|```/g, "").trim();
      return JSON.parse(clean);
    } catch (error) {
      console.error('Analysis error:', error);
      return {
        summary: "Analysis unavailable",
        keywords: [],
        entities: [],
        topic: "General"
      };
    }
  };

  const handleFileUpload = async (e) => {
    const files = Array.from(e.target.files);
    setIsAnalyzing(true);

    for (const file of files) {
      const reader = new FileReader();
      
      reader.onload = async (event) => {
        const content = event.target.result;
        let text = content;
        
        if (file.type === 'application/pdf') {
          text = `[PDF Content from ${file.name}]\n\nThis is a simulated PDF text extraction. In a real implementation, this would contain the extracted text from the PDF document.`;
        }

        const analysis = await analyzeDocument(text, file.name);
        
        const newDoc = {
          id: Date.now() + Math.random(),
          title: file.name.replace(/\.[^/.]+$/, ""),
          content: text,
          uploadDate: new Date().toISOString(),
          fileType: file.type,
          tags: [analysis.topic],
          ...analysis
        };

        setDocuments(prev => {
          const updated = [...prev, newDoc];
          window.storage.set(`doc:${newDoc.id}`, JSON.stringify(newDoc));
          return updated;
        });
      };

      if (file.type === 'application/pdf') {
        reader.readAsArrayBuffer(file);
      } else {
        reader.readAsText(file);
      }
    }

    setIsAnalyzing(false);
    setShowUpload(false);
  };

  const regenerateAnalysis = async (doc) => {
    setIsAnalyzing(true);
    const analysis = await analyzeDocument(doc.content, doc.title);
    
    const updated = documents.map(d => 
      d.id === doc.id ? { ...d, ...analysis, tags: [analysis.topic, ...d.tags.slice(1)] } : d
    );
    
    setDocuments(updated);
    await window.storage.set(`doc:${doc.id}`, JSON.stringify({ ...doc, ...analysis }));
    
    if (selectedDoc?.id === doc.id) {
      setSelectedDoc({ ...doc, ...analysis });
    }
    
    setIsAnalyzing(false);
  };

  const addNote = async (docId, note) => {
    const docNotes = notes[docId] || [];
    const newNote = {
      id: Date.now(),
      text: note,
      timestamp: new Date().toISOString()
    };
    
    const updated = [...docNotes, newNote];
    setNotes(prev => ({ ...prev, [docId]: updated }));
    await window.storage.set(`notes:${docId}`, JSON.stringify(updated));
  };

  const linkDocuments = async (docId, linkedDocId) => {
    const docLinks = links[docId] || [];
    if (!docLinks.includes(linkedDocId)) {
      const updated = [...docLinks, linkedDocId];
      setLinks(prev => ({ ...prev, [docId]: updated }));
      await window.storage.set(`links:${docId}`, JSON.stringify(updated));
    }
  };

  const deleteDocument = async (docId) => {
    setDocuments(prev => prev.filter(d => d.id !== docId));
    await window.storage.delete(`doc:${docId}`);
    await window.storage.delete(`notes:${docId}`);
    await window.storage.delete(`links:${docId}`);
    if (selectedDoc?.id === docId) setSelectedDoc(null);
  };

  const addTag = async (docId, tag) => {
    const updated = documents.map(d => 
      d.id === docId && !d.tags.includes(tag) 
        ? { ...d, tags: [...d.tags, tag] } 
        : d
    );
    setDocuments(updated);
    const doc = updated.find(d => d.id === docId);
    await window.storage.set(`doc:${docId}`, JSON.stringify(doc));
  };

  const filteredDocs = documents.filter(doc => {
    const matchesSearch = doc.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         doc.summary?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         doc.keywords?.some(k => k.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesTag = !filterTag || doc.tags.includes(filterTag);
    return matchesSearch && matchesTag;
  });

  const allTags = [...new Set(documents.flatMap(d => d.tags))];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BookOpen className="w-8 h-8 text-blue-600" />
            <h1 className="text-2xl font-bold text-slate-800">Research Hub</h1>
          </div>
          <button
            onClick={() => setShowUpload(!showUpload)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Upload className="w-5 h-5" />
            Upload Documents
          </button>
        </div>
      </header>

      {/* Upload Modal */}
      {showUpload && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold text-slate-800">Upload Documents</h2>
              <button onClick={() => setShowUpload(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-6 h-6" />
              </button>
            </div>
            <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center">
              <Upload className="w-12 h-12 text-slate-400 mx-auto mb-3" />
              <p className="text-slate-600 mb-4">Upload PDF or text files</p>
              <input
                type="file"
                multiple
                accept=".pdf,.txt"
                onChange={handleFileUpload}
                className="hidden"
                id="fileInput"
              />
              <label
                htmlFor="fileInput"
                className="inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer transition-colors"
              >
                Choose Files
              </label>
            </div>
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Search and Filters */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input
                type="text"
                placeholder="Search documents, keywords, or topics..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div className="flex items-center gap-2">
              <Filter className="w-5 h-5 text-slate-400" />
              <select
                value={filterTag}
                onChange={(e) => setFilterTag(e.target.value)}
                className="px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">All Topics</option>
                {allTags.map(tag => (
                  <option key={tag} value={tag}>{tag}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {isAnalyzing && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6 flex items-center gap-3">
            <RefreshCw className="w-5 h-5 text-blue-600 animate-spin" />
            <p className="text-blue-800">Analyzing documents with AI...</p>
          </div>
        )}

        <div className="grid lg:grid-cols-3 gap-6">
          {/* Documents List */}
          <div className="lg:col-span-2 space-y-4">
            {filteredDocs.length === 0 ? (
              <div className="bg-white rounded-xl shadow-sm p-12 text-center">
                <FileText className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                <h3 className="text-xl font-semibold text-slate-600 mb-2">No documents yet</h3>
                <p className="text-slate-500">Upload your first research document to get started</p>
              </div>
            ) : (
              filteredDocs.map(doc => (
                <div
                  key={doc.id}
                  className={`bg-white rounded-xl shadow-sm p-6 cursor-pointer transition-all hover:shadow-md ${
                    selectedDoc?.id === doc.id ? 'ring-2 ring-blue-500' : ''
                  }`}
                  onClick={() => setSelectedDoc(doc)}
                >
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-slate-800 mb-1">{doc.title}</h3>
                      <p className="text-sm text-slate-500">
                        {new Date(doc.uploadDate).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={(e) => { e.stopPropagation(); regenerateAnalysis(doc); }}
                        className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                        title="Regenerate analysis"
                      >
                        <RefreshCw className="w-4 h-4" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteDocument(doc.id); }}
                        className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  <p className="text-slate-600 mb-3 line-clamp-2">{doc.summary}</p>

                  <div className="flex flex-wrap gap-2 mb-3">
                    {doc.tags?.map(tag => (
                      <span key={tag} className="px-3 py-1 bg-blue-100 text-blue-700 text-xs rounded-full font-medium">
                        {tag}
                      </span>
                    ))}
                  </div>

                  {doc.keywords?.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {doc.keywords.slice(0, 5).map(keyword => (
                        <span key={keyword} className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">
                          {keyword}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Detail Panel */}
          {selectedDoc && (
            <div className="lg:col-span-1">
              <div className="bg-white rounded-xl shadow-sm p-6 sticky top-6">
                <h2 className="text-xl font-bold text-slate-800 mb-4">{selectedDoc.title}</h2>

                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                    <FileText className="w-4 h-4" />
                    Summary
                  </h3>
                  <p className="text-slate-600 text-sm">{selectedDoc.summary}</p>
                </div>

                {selectedDoc.entities?.length > 0 && (
                  <div className="mb-6">
                    <h3 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                      <Tag className="w-4 h-4" />
                      Key Entities
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {selectedDoc.entities.map(entity => (
                        <span key={entity} className="px-2 py-1 bg-purple-100 text-purple-700 text-xs rounded">
                          {entity}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" />
                    Notes
                  </h3>
                  <div className="space-y-2 mb-2 max-h-40 overflow-y-auto">
                    {notes[selectedDoc.id]?.map(note => (
                      <div key={note.id} className="bg-yellow-50 p-2 rounded text-sm">
                        <p className="text-slate-700">{note.text}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          {new Date(note.timestamp).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>
                  <input
                    type="text"
                    placeholder="Add a note..."
                    onKeyPress={(e) => {
                      if (e.key === 'Enter' && e.target.value.trim()) {
                        addNote(selectedDoc.id, e.target.value);
                        e.target.value = '';
                      }
                    }}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                    <Link className="w-4 h-4" />
                    Linked Documents
                  </h3>
                  <select
                    onChange={(e) => {
                      if (e.target.value) {
                        linkDocuments(selectedDoc.id, e.target.value);
                        e.target.value = '';
                      }
                    }}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm mb-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  >
                    <option value="">Link a document...</option>
                    {documents.filter(d => d.id !== selectedDoc.id).map(doc => (
                      <option key={doc.id} value={doc.id}>{doc.title}</option>
                    ))}
                  </select>
                  <div className="space-y-1">
                    {links[selectedDoc.id]?.map(linkedId => {
                      const linkedDoc = documents.find(d => d.id === linkedId);
                      return linkedDoc ? (
                        <div
                          key={linkedId}
                          className="text-sm text-blue-600 hover:bg-blue-50 p-2 rounded cursor-pointer"
                          onClick={() => setSelectedDoc(linkedDoc)}
                        >
                          → {linkedDoc.title}
                        </div>
                      ) : null;
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResearchHub;