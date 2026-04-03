import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Mic, Video, MessageSquare, Brain, Sparkles,
  Upload, Languages, Loader2, Zap, RefreshCw,
  History, X, Activity, ChevronDown, ArrowRight,
  Clock, Globe, Trash2, CheckCircle2, Copy, Share2,
  Settings, Image, KeyboardIcon, BarChart2
} from 'lucide-react';

const API_URL = '';

const LANGUAGES = [
  'english','hindi','bengali','tamil','telugu',
  'marathi','kannada','malayalam','french','german',
  'spanish','portuguese','italian'
];

const MODES = [
  { id:'text',    label:'Text',    icon:MessageSquare },
  { id:'context', label:'Context', icon:Brain         },
  { id:'audio',   label:'Speech',  icon:Mic           },
  { id:'video',   label:'Video',   icon:Video         },
  { id:'emotion', label:'Emotion', icon:Sparkles      },
];

const EMOTION_COLORS = {
  joy:'#0060ad', sadness:'#3b82f6', anger:'#ef4444',
  fear:'#a855f7', surprise:'#f59e0b', disgust:'#f97316', neutral:'#94a3b8',
};
const EMOTION_ICONS = {
  joy:'😊', sadness:'😢', anger:'😠',
  fear:'😨', surprise:'😲', disgust:'🤢', neutral:'😐',
};

const EMPTY_MODE_STATE = {
  sourceText:'', translatedText:'', emotion:null, perf:null,
  mediaURL:null, mediaType:null, fileName:null, context:[], ctxInfluence:0,
};

export default function TranslationApp() {
  const [mode, setMode]         = useState('text');
  const [sourceLang, setSource] = useState('english');
  const [targetLang, setTarget] = useState('hindi');
  const [useContext, setUseCtx] = useState(false);
  const [loading, setLoading]   = useState(false);
  const [history, setHistory]   = useState([]);
  const [showHistory, setShowH] = useState(false);
  const [visibleWords, setVW]   = useState(0);
  const [animating, setAnim]    = useState(false);
  const [toastMsg, setToast]    = useState('');
  const [charCount, setCharCount] = useState(0);

  const sessionIdRef = useRef('sess_' + Date.now() + '_' + Math.random().toString(36).slice(2,8));
  const sessionId = sessionIdRef.current;

  const [modeStates, setModeStates] = useState({
    text:    { ...EMPTY_MODE_STATE },
    context: { ...EMPTY_MODE_STATE },
    audio:   { ...EMPTY_MODE_STATE },
    video:   { ...EMPTY_MODE_STATE },
    emotion: { ...EMPTY_MODE_STATE },
  });

  const cur = modeStates[mode];
  const setModeField = (field, value) =>
    setModeStates(prev => ({ ...prev, [mode]: { ...prev[mode], [field]: value } }));

  const fileRef  = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => { setAnim(false); setVW(0); }, [mode]);

  useEffect(() => {
    if (!animating || !cur.translatedText) return;
    const words = cur.translatedText.split(' ');
    if (visibleWords >= words.length) { setAnim(false); return; }
    timerRef.current = setTimeout(() => setVW(v => v + 1), 55);
    return () => clearTimeout(timerRef.current);
  }, [animating, visibleWords, cur.translatedText]);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2500);
  };

  const refreshHistory = useCallback(async () => {
    const id = sessionIdRef.current;
    if (!id) return;
    try {
      const res  = await fetch(`${API_URL}/session/${id}/history?limit=50`);
      const data = await res.json();
      if (Array.isArray(data.history)) setHistory(data.history);
    } catch (err) { console.error('History fetch failed:', err); }
  }, []);

  const handleTranslate = async (file = null) => {
    if (!cur.sourceText && !file) return;
    setLoading(true);
    setModeField('translatedText', '');
    setModeField('emotion', null);
    setModeField('ctxInfluence', 0);
    setVW(0); setAnim(false);

    try {
      const fd = new FormData();
      fd.append('source_lang', sourceLang);
      fd.append('target_lang', targetLang);
      fd.append('session_id', sessionIdRef.current);
      fd.append('use_context', mode === 'context' ? String(useContext) : 'false');
      if (file) {
        fd.append(mode === 'audio' ? 'audio' : 'video', file);
      } else {
        fd.append('text', cur.sourceText);
      }

      const res  = await fetch(`${API_URL}/translate`, { method: 'POST', body: fd });
      const data = await res.json();

      if (data.error) { showToast('⚠️ ' + data.error); return; }

      const ctxSentences = data.context_sentences || [];
      const ctxInfluence = (mode === 'context' && data.context_used && ctxSentences.length > 0)
        ? Math.min(ctxSentences.length / 2, 1) : 0;

      setModeStates(prev => ({
        ...prev,
        [mode]: {
          ...prev[mode],
          sourceText:     file ? (data.original || '') : prev[mode].sourceText,
          translatedText: data.translated || '',
          emotion:        data.emotion    || null,
          perf:           data.performance || null,
          ctxInfluence,
          context: (mode === 'context' && ctxSentences.length > 0)
            ? ctxSentences : prev[mode].context,
        }
      }));

      setAnim(true); setVW(0);
      await refreshHistory();
    } catch (err) {
      console.error('Translation error:', err);
      showToast('⚠️ Connection failed. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  const handleFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setModeStates(prev => ({
      ...prev,
      [mode]: { ...prev[mode], mediaURL: url, mediaType: mode, fileName: file.name }
    }));
    handleTranslate(file);
  };

  const handleRefresh = async () => {
    if (!window.confirm('Clear all translations and start fresh?')) return;
    const fd = new FormData();
    fd.append('session_id', sessionIdRef.current);
    await fetch(`${API_URL}/session/clear`, { method: 'POST', body: fd }).catch(() => {});
    setModeStates({
      text:    { ...EMPTY_MODE_STATE },
      context: { ...EMPTY_MODE_STATE },
      audio:   { ...EMPTY_MODE_STATE },
      video:   { ...EMPTY_MODE_STATE },
      emotion: { ...EMPTY_MODE_STATE },
    });
    setHistory([]);
    setShowH(false);
    showToast('✅ Session cleared');
  };

  const loadHistory = async () => {
    await refreshHistory();
    setShowH(true);
  };

  const handleCopy = () => {
    if (cur.translatedText) {
      navigator.clipboard.writeText(cur.translatedText);
      showToast('✅ Copied to clipboard');
    }
  };

  const words = cur.translatedText ? cur.translatedText.split(' ') : [];

  return (
    <div style={styles.root}>
      {/* ── Mesh Background ── */}
      <div style={styles.meshBg} />

      {/* ── TOAST ── */}
      {toastMsg && (
        <div style={styles.toast}>
          <div style={styles.toastDot}><CheckCircle2 size={14} color="#fff"/></div>
          <span style={styles.toastText}>{toastMsg}</span>
          <button style={styles.toastUndo} onClick={() => setToast('')}>DISMISS</button>
        </div>
      )}

      {/* ── TOP NAV ── */}
      <header style={styles.header}>
        <div style={styles.headerInner}>
          {/* Left: Logo + Nav */}
          <div style={styles.headerLeft}>
            <div style={styles.logoWrap}>
              <div style={styles.logoBox}><Languages size={18} color="#fff"/></div>
              <span style={styles.logoText}>Context Translator</span>
            </div>
            <nav style={styles.nav}>
              {MODES.map(m => (
                <button
                  key={m.id}
                  onClick={() => setMode(m.id)}
                  style={{
                    ...styles.navItem,
                    ...(mode === m.id ? styles.navItemActive : {}),
                  }}
                >
                  {m.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Right: Session + Actions */}
          <div style={styles.headerRight}>
            <div style={styles.sessionPill}>
              <span style={styles.sessionDotOuter}>
                <span style={styles.sessionDotInner}/>
              </span>
              <span style={styles.sessionText}>Session</span>
            </div>
            <button onClick={loadHistory} style={styles.iconBtn} title="History">
              <History size={20}/>
              {history.length > 0 && <span style={styles.histBadge}>{history.length}</span>}
            </button>
            <button onClick={handleRefresh} style={styles.iconBtn} title="Reset">
              <RefreshCw size={20}/>
            </button>
          </div>
        </div>
      </header>

      {/* ── MAIN ── */}
      <main style={styles.main}>

        {/* Hero */}
        <div style={styles.hero}>
          <h1 style={styles.heroTitle}>
            Context-Aware <span style={styles.heroAccent}>Translation</span> &amp; Emotion
          </h1>
          <p style={styles.heroSub}>
            Harnessing advanced neural processing to bridge languages with sentiment and cultural nuance.
          </p>
        </div>

        {/* ── MODE GRID ── */}
        <div style={styles.modeGrid}>
          {MODES.map(m => {
            const Icon = m.icon;
            const active = mode === m.id;
            return (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                style={{ ...styles.modeCard, ...(active ? styles.modeCardActive : {}) }}
              >
                <Icon size={32} style={{ color: active ? '#0060ad' : '#9ca3af', marginBottom: 10, transition: 'color .2s' }}/>
                <span style={{ ...styles.modeLabel, ...(active ? styles.modeLabelActive : {}) }}>
                  {m.label}
                </span>
              </button>
            );
          })}
        </div>

        {/* ── WORKSPACE ── */}
        <div style={styles.workspace}>

          {/* SOURCE CARD */}
          <div style={styles.card}>
            {/* Card Header */}
            <div style={styles.cardHeader}>
              <div style={styles.cardHeaderLeft}>
  <span style={styles.outputBadge}>
    {mode === 'emotion' ? 'Emotion Analysis' : 'Neural Result'}
  </span>
  {mode !== 'emotion' && <LangSelect value={targetLang} onChange={setTarget}/>}
</div>
              <button
                style={styles.clearBtn}
                onClick={() => { setModeField('sourceText',''); setCharCount(0); }}
                title="Clear"
              >
                <X size={16}/>
              </button>
            </div>

            {/* Input area */}
            <div style={styles.cardBody}>
              {mode === 'audio' || mode === 'video' ? (
                <FileZone
                  mode={mode}
                  mediaURL={cur.mediaURL}
                  mediaType={cur.mediaType}
                  fileName={cur.fileName}
                  fileRef={fileRef}
                  onFile={handleFile}
                  onClear={() => {
                    setModeStates(prev => ({
                      ...prev,
                      [mode]: { ...prev[mode], mediaURL:null, mediaType:null, fileName:null }
                    }));
                    if (fileRef.current) fileRef.current.value = '';
                  }}
                />
              ) : (
                <textarea
                  style={styles.textarea}
                  value={cur.sourceText}
                  onChange={e => {
                    setModeField('sourceText', e.target.value);
                    setCharCount(e.target.value.length);
                  }}
                  placeholder="Describe your thought here..."
                  onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleTranslate(); }}
                />
              )}
            </div>

            {/* Context toggle (context mode) */}
            {mode === 'context' && (
              <div style={styles.ctxToggleWrap}>
                <label style={styles.ctxToggle}>
                  <input
                    type="checkbox"
                    checked={useContext}
                    onChange={e => setUseCtx(e.target.checked)}
                    style={{ display:'none' }}
                  />
                  <div style={{ ...styles.toggleTrack, ...(useContext ? styles.toggleTrackOn : {}) }}>
                    <div style={{ ...styles.toggleThumb, ...(useContext ? styles.toggleThumbOn : {}) }}/>
                  </div>
                  <div>
                    <div style={styles.ctxLabel}>Use conversation context</div>
                    <div style={styles.ctxHint}>
                      {useContext ? '✅ Uses last 2 translations for accuracy' : '⚪ Each translation is independent'}
                    </div>
                  </div>
                </label>
              </div>
            )}

            {/* Context panel */}
            {mode === 'context' && (
              <div style={styles.ctxPanel}>
                <div style={styles.ctxPanelHead}>
                  <span style={styles.ctxPanelTitle}>Context ({cur.context.length} sentences)</span>
                  <button style={styles.ctxClearBtn} onClick={() => setModeField('context', [])}>Clear</button>
                </div>
                {cur.context.length === 0 ? (
                  <p style={styles.mutedText}>
                    {useContext ? 'No context yet — translate something first!' : 'Enable the toggle to use conversation history.'}
                  </p>
                ) : (
                  cur.context.map((c, i) => (
                    <div key={i} style={styles.ctxItem}>
                      <span style={styles.ctxItemNum}>#{i+1}</span> {c}
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Transcription */}
            {(mode === 'audio' || mode === 'video') && cur.sourceText && (
              <div style={styles.transcribed}>
                <span style={styles.transcribedLabel}>Transcribed Text</span>
                <p style={styles.transcribedText}>{cur.sourceText}</p>
              </div>
            )}

            {/* Card Footer */}
            <div style={styles.cardFooter}>
              <div style={{ display:'flex', gap:8 }}>
                <button style={styles.footerIconBtn} title="Voice input"><Mic size={17}/></button>
                <button style={styles.footerIconBtn} title="Image input"><Image size={17}/></button>
              </div>
              <span style={styles.charCount}>{charCount} / 5000</span>
            </div>
          </div>

          {/* OUTPUT CARD */}
          <div style={styles.cardOutput}>
            {/* Card Header */}
            <div style={styles.cardHeader}>
              <div style={styles.cardHeaderLeft}>
                <span style={styles.outputBadge}>Neural Result</span>
                <LangSelect value={targetLang} onChange={setTarget}/>
              </div>
              <div style={{ display:'flex', gap:4 }}>
                <button style={styles.clearBtn} onClick={handleCopy} title="Copy"><Copy size={16}/></button>
                <button style={styles.clearBtn} title="Share"><Share2 size={16}/></button>
              </div>
            </div>

            {/* Media preview (audio/video) */}
            {(mode === 'audio' || mode === 'video') && cur.mediaURL && (
              <div style={styles.mediaOutWrap}>
                <div style={styles.mediaOutHead}>
                  <span>{mode === 'video' ? '🎬' : '🎤'} {cur.fileName}</span>
                </div>
                {mode === 'video'
                  ? <video src={cur.mediaURL} controls style={styles.mediaVideo}/>
                  : <audio src={cur.mediaURL} controls style={styles.mediaAudio}/>
                }
              </div>
            )}

           <div style={{ ...styles.outputBody, ...(mode === 'emotion' ? { minHeight: 0, padding: '0' } : {}) }}>
  {loading ? (
    <div style={styles.shimmerWrap}>
      <div style={styles.shimmerLine}/>
      <div style={{ ...styles.shimmerLine, width:'75%' }}/>
      <div style={{ ...styles.shimmerLine, width:'55%' }}/>
    </div>
  ) : mode === 'emotion' ? (
    !cur.emotion && (
      <div style={styles.emptyState}>
        <Sparkles size={28} style={{ opacity:.25 }}/>
        <p style={{ opacity:.35, fontSize:14, fontStyle:'italic' }}>
          Emotion analysis will appear below…
        </p>
      </div>
    )
  ) : cur.translatedText ? (
    <div style={styles.translatedText}>
      {words.slice(0, visibleWords).map((w, i) => (
        <span key={i} style={{ ...styles.word, animationDelay:`${i*0.03}s` }}>
          {w}{' '}
        </span>
      ))}
      {animating && visibleWords < words.length && (
        <span style={styles.caret}/>
      )}
    </div>
  ) : (
    <div style={styles.emptyState}>
      <ArrowRight size={28} style={{ opacity:.25 }}/>
      <p style={{ opacity:.35, fontSize:14, fontStyle:'italic' }}>
        Translation will appear here…
      </p>
    </div>
  )}

  {cur.emotion && mode !== 'emotion' && (
    <div style={styles.emotionOverlay}>
      <span style={styles.emotionBadge}>
        {EMOTION_ICONS[cur.emotion.emotion?.toLowerCase()] || '😐'}{' '}
        {(cur.emotion.confidence * 100).toFixed(0)}% {cur.emotion.emotion?.toUpperCase()}
      </span>
      {cur.ctxInfluence > 0 && (
        <span style={styles.contextBadge}>
          <Brain size={12}/> {Math.round(cur.ctxInfluence * 100)}% CONTEXT
        </span>
      )}
    </div>
  )}
</div>

            {/* Context influence bar */}
            {cur.ctxInfluence > 0 && mode !== 'emotion' && (
  <div style={styles.influenceBar}>
                <div style={styles.influenceHead}>
                  <span>Context Influence</span>
                  <strong>{Math.round(cur.ctxInfluence * 100)}%</strong>
                </div>
                <div style={styles.influenceTrack}>
                  <div style={{ ...styles.influenceFill, width:`${cur.ctxInfluence*100}%` }}>
                    <div style={styles.shimmerFill}/>
                  </div>
                </div>
                <div style={styles.influenceNote}>
                  Used {Math.round(cur.ctxInfluence * 2)} previous sentence{cur.ctxInfluence * 2 !== 1 ? 's' : ''} as context
                </div>
              </div>
            )}

            {/* Perf card */}
            {cur.perf && mode !== 'emotion' && <PerfCard perf={cur.perf}/>}

            {/* Emotion detail card */}
            {cur.emotion && <EmotionCard emotion={cur.emotion}/>}

            {/* Translate button */}
            <div style={styles.translateBtnWrap}>
              <button
                style={{
                  ...styles.translateBtn,
                  ...(loading || (!cur.sourceText && mode !== 'audio' && mode !== 'video')
                    ? styles.translateBtnDisabled : {})
                }}
                onClick={() => handleTranslate()}
                disabled={loading || (!cur.sourceText && mode !== 'audio' && mode !== 'video')}
              >
                <span style={styles.translateBtnInner}>
                  {loading
                    ? <><Loader2 size={18} style={styles.spin}/> Processing…</>
                    : mode === 'emotion'
                  ? <>Analyze Emotion <Sparkles size={18}/></>
                  : <>Translate Content <ArrowRight size={18}/></>
                  }
                </span>
                <div style={styles.translateBtnShine}/>
              </button>
            </div>
          </div>
        </div>

        {/* ── HISTORY STRIP ── */}
        {history.length > 0 && (
          <div style={styles.historyStrip}>
            <div style={styles.historyStripHead}>
              <div style={styles.historyStripTitle}>
                <History size={15}/>
                <span>Recent Translations</span>
                <span style={styles.histCount}>{history.length} total</span>
              </div>
              <button style={styles.viewAllBtn} onClick={loadHistory}>View All</button>
            </div>
            <div style={styles.historyGrid}>
              {[...history].reverse().slice(0, 3).map((item, i) => (
                <div key={i} style={{ ...styles.histItem, animationDelay:`${i*0.08}s` }}>
                  <div style={styles.histItemTop}>
                    <Globe size={11} style={{ color:'#9ca3af' }}/>
                    <span style={styles.histLangs}>{item.source_lang} → {item.target_lang}</span>
                    {item.emotion && (
                      <span style={{ color: EMOTION_COLORS[item.emotion.emotion] || '#94a3b8', fontSize:14 }}>
                        {EMOTION_ICONS[item.emotion.emotion] || '😐'}
                      </span>
                    )}
                    <span style={styles.histTime}>
                      <Clock size={10}/>
                      {new Date(item.timestamp).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' })}
                    </span>
                  </div>
                  <div style={styles.histOrig}>{item.original}</div>
                  <div style={styles.histTrans}>{item.translated}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── FOOTER ── */}
        <footer style={styles.footer}>
          <div style={styles.footerServices}>
            {[
              { icon:<Activity size={18}/>, label:'MyMemory · LibreTranslate · Lingva' },
              { icon:<Mic size={18}/>,      label:'Whisper Tiny' },
              { icon:<Sparkles size={18}/>, label:'DistilRoBERTa Emotion' },
            ].map((s, i) => (
              <div key={i} style={styles.footerService}>
                {s.icon}
                <span style={styles.footerServiceLabel}>{s.label}</span>
              </div>
            ))}
          </div>
          <div style={styles.footerSession}>
            <span style={styles.footerSessionText}>
              Session: {sessionId.slice(0,16)}…
            </span>
          </div>
        </footer>
      </main>

      {/* ── HISTORY MODAL ── */}
      {showHistory && (
        <div style={styles.overlay} onClick={() => setShowH(false)}>
          <div style={styles.modal} onClick={e => e.stopPropagation()}>
            <div style={styles.modalHead}>
              <h2 style={styles.modalTitle}>
                Translation History
                <span style={styles.modalCount}>{history.length} entries</span>
              </h2>
              <div style={{ display:'flex', gap:8 }}>
                <button style={{ ...styles.iconBtn, color:'#ef4444' }} onClick={handleRefresh}>
                  <Trash2 size={16}/>
                </button>
                <button style={styles.iconBtn} onClick={() => setShowH(false)}>
                  <X size={16}/>
                </button>
              </div>
            </div>
            <div style={styles.modalBody}>
              {history.length === 0 ? (
                <div style={styles.emptyHistory}>
                  <div style={{ fontSize:42, marginBottom:12 }}>🌐</div>
                  <p style={styles.mutedText}>No history yet. Start translating!</p>
                </div>
              ) : (
                [...history].reverse().map((item, i) => (
                  <div
                    key={i}
                    style={{
                      ...styles.histModalItem,
                      borderLeftColor: EMOTION_COLORS[item.emotion?.emotion] || '#0060ad',
                      animationDelay: `${i*0.04}s`
                    }}
                  >
                    <div style={styles.histModalTop}>
                      <span style={styles.histModalNum}>#{history.length - i}</span>
                      <span style={styles.histTime}>
                        <Clock size={10}/>
                        {new Date(item.timestamp).toLocaleTimeString()}
                      </span>
                      <span style={styles.histLangBadge}>{item.source_lang} → {item.target_lang}</span>
                      {item.emotion && (
                        <span style={{ marginLeft:'auto', fontFamily:'monospace', fontSize:12,
                          color: EMOTION_COLORS[item.emotion.emotion] || '#94a3b8', fontWeight:700 }}>
                          {EMOTION_ICONS[item.emotion.emotion] || '😐'} {item.emotion.emotion}
                          <span style={{ opacity:.6, marginLeft:3 }}>
                            ({(item.emotion.confidence*100).toFixed(0)}%)
                          </span>
                        </span>
                      )}
                    </div>
                    <div style={styles.histOrigText}>{item.original}</div>
                    <div style={styles.histTransText}>{item.translated}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Manrope', sans-serif; }

        @keyframes shimmerMove {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes wordIn {
          from { opacity:0; transform:translateY(4px); }
          to   { opacity:1; transform:translateY(0); }
        }
        @keyframes blink {
          0%,50%  { opacity:1; }
          51%,100%{ opacity:0; }
        }
        @keyframes spin {
          from { transform:rotate(0deg); }
          to   { transform:rotate(360deg); }
        }
        @keyframes toastIn {
          from { opacity:0; transform:translateX(-50%) translateY(12px); }
          to   { opacity:1; transform:translateX(-50%) translateY(0); }
        }
        @keyframes fadeIn {
          from { opacity:0; }
          to   { opacity:1; }
        }
        @keyframes slideUp {
          from { opacity:0; transform:translateY(18px); }
          to   { opacity:1; transform:translateY(0); }
        }
        @keyframes ping {
          0%   { transform:scale(1); opacity:.75; }
          75%,100% { transform:scale(2); opacity:0; }
        }

        .shimmer-line {
          background: linear-gradient(90deg, #f0f4f7 25%, #e3e9ed 50%, #f0f4f7 75%);
          background-size: 200% 100%;
          animation: shimmerMove 2s infinite linear;
          border-radius: 999px;
          height: 22px;
        }
        .word-anim {
          display: inline-block;
          animation: wordIn 0.35s ease both;
        }
        .translate-shine {
          position:absolute; inset:0;
          background: linear-gradient(90deg, transparent, rgba(255,255,255,.2), transparent);
          transform: translateX(-100%);
          transition: transform 0.9s ease;
        }
        .translate-btn-wrap:hover .translate-shine {
          transform: translateX(100%);
        }
      `}</style>
    </div>
  );
}

/* ─────────────────────────────────────────
   SUB-COMPONENTS
───────────────────────────────────────── */

function LangSelect({ value, onChange }) {
  return (
    <div style={styles.langWrap}>
      <select
        style={styles.langSel}
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        {LANGUAGES.map(l => (
          <option key={l} value={l}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>
        ))}
      </select>
      <ChevronDown size={13} style={styles.langChev}/>
    </div>
  );
}

function FileZone({ mode, mediaURL, mediaType, fileName, fileRef, onFile, onClear }) {
  return (
    <div style={styles.fileZone}>
      {mediaURL ? (
        <div style={styles.mediaWrap}>
          <div style={styles.mediaTop}>
            <span style={styles.mediaName}>📁 {fileName}</span>
            <button style={styles.clearBtn} onClick={onClear}><X size={13}/> Remove</button>
          </div>
          {mediaType === 'video'
            ? <video src={mediaURL} controls style={styles.mediaVideo}/>
            : <audio src={mediaURL} controls style={styles.mediaAudio}/>
          }
          <button style={styles.reuploadBtn} onClick={() => fileRef.current?.click()}>
            <Upload size={13}/> Upload different file
          </button>
        </div>
      ) : (
        <button style={styles.uploadBtn} onClick={() => fileRef.current?.click()}>
          <Upload size={32} style={{ opacity:.4, marginBottom:10 }}/>
          <span style={styles.uploadMain}>Click to upload {mode} file</span>
          <span style={styles.uploadSub}>
            {mode === 'audio' ? 'MP3 · WAV · M4A · OGG' : 'MP4 · MOV · AVI · WebM'}
          </span>
        </button>
      )}
      <input
        ref={fileRef} type="file"
        accept={mode === 'audio' ? 'audio/*' : 'video/*'}
        onChange={onFile}
        style={{ display:'none' }}
      />
    </div>
  );
}

function PerfCard({ perf }) {
  const method = perf.method || 'api';
  const methodColor = {
    cache:'#22c55e', mymemory:'#0060ad', libretranslate:'#a855f7',
    lingva:'#f59e0b', local_nllb:'#ef4444',
  }[method] || '#94a3b8';

  return (
    <div style={styles.perfCard}>
      <div style={styles.perfHead}>
        <Activity size={13}/>
        <span style={styles.perfTitle}>Performance</span>
        <span style={{ ...styles.methodBadge, background:`${methodColor}18`, color:methodColor, border:`1px solid ${methodColor}33` }}>
          {method}
        </span>
      </div>
      <div style={styles.perfGrid}>
        {perf.transcription_ms > 0 && (
          <div style={styles.perfItem}>
            <span>Transcription</span><strong>{perf.transcription_ms.toFixed(0)}ms</strong>
          </div>
        )}
        <div style={styles.perfItem}>
          <span>Translation</span><strong>{perf.translation_ms.toFixed(0)}ms</strong>
        </div>
        <div style={styles.perfItem}>
          <span>Emotion</span><strong>{perf.emotion_detection_ms?.toFixed(0)||0}ms</strong>
        </div>
        <div style={{ ...styles.perfItem, ...styles.perfTotal }}>
          <span>Total</span><strong style={{ fontSize:15 }}>{perf.total_ms.toFixed(0)}ms</strong>
        </div>
      </div>
    </div>
  );
}
function EmotionCard({ emotion }) {
  const EMOS = ['joy','sadness','anger','fear','surprise','disgust','neutral']; // ← added disgust
  const scores   = emotion.scores || {};
  const domColor = EMOTION_COLORS[emotion.emotion?.toLowerCase()] || '#94a3b8';
  const needle   = (emotion.confidence * 180) - 90;

  return (
    <div style={styles.emoCard}>
      {/* Header */}
      <div style={styles.emoHead}>
        <span style={{ fontSize:36, lineHeight:1 }}>
          {EMOTION_ICONS[emotion.emotion?.toLowerCase()] || '😐'}
        </span>
        <div>
          <div style={{ ...styles.emoName, color:domColor }}>
            {emotion.emotion?.toUpperCase()}
          </div>
          <div style={styles.emoConf}>{(emotion.confidence*100).toFixed(1)}% confidence</div>
        </div>
      </div>

      {/* ── NEW: Nuanced emotion badge ── */}
      {emotion.nuanced_emotion && (
        <div style={{
          padding: '8px 14px',
          background: `${domColor}12`,
          border: `1px solid ${domColor}30`,
          borderRadius: 10,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontSize:10, fontWeight:900, letterSpacing:'0.12em',
              textTransform:'uppercase', color:'#94a3b8', marginBottom:3 }}>
              Nuanced Emotion
            </div>
            <div style={{ fontSize:15, fontWeight:800, color:domColor }}>
              {emotion.nuanced_emotion}
            </div>
            {emotion.nuanced_source && (
              <div style={{ fontSize:10, color:'#94a3b8', fontFamily:'monospace', marginTop:2 }}>
                via {emotion.nuanced_source}
              </div>
            )}
          </div>
          <div style={{ textAlign:'right' }}>
            <div style={{ fontSize:10, fontWeight:900, letterSpacing:'0.12em',
              textTransform:'uppercase', color:'#94a3b8', marginBottom:3 }}>
              Intensity
            </div>
            <div style={{ fontSize:13, fontWeight:800,
              color: emotion.intensity === 'intense' ? '#ef4444'
                   : emotion.intensity === 'high'    ? '#f59e0b'
                   : emotion.intensity === 'moderate'? '#0060ad' : '#94a3b8'
            }}>
              {emotion.intensity?.toUpperCase()}
            </div>
          </div>
        </div>
      )}

      {/* ── NEW: Valence / Arousal / Quadrant ── */}
      {emotion.valence !== undefined && (
        <div style={{
          display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8,
        }}>
          {[
            { label:'Valence', value: emotion.valence, suffix:'', hint: emotion.valence >= 0 ? '😊 Positive' : '😔 Negative' },
            { label:'Arousal', value: emotion.arousal, suffix:'', hint: emotion.arousal >= 0 ? '⚡ Excited' : '😴 Calm' },
          ].map(({ label, value, hint }) => (
            <div key={label} style={{
              padding:'10px 12px',
              background:'rgba(0,0,0,.03)',
              border:'1px solid rgba(0,0,0,.07)',
              borderRadius:10, textAlign:'center'
            }}>
              <div style={{ fontSize:10, fontWeight:900, letterSpacing:'0.12em',
                textTransform:'uppercase', color:'#94a3b8', marginBottom:4 }}>
                {label}
              </div>
              <div style={{ fontSize:18, fontWeight:800, color:domColor }}>
                {value > 0 ? '+' : ''}{value.toFixed(2)}
              </div>
              <div style={{ fontSize:10, color:'#94a3b8', marginTop:2 }}>{hint}</div>
            </div>
          ))}
          <div style={{
            padding:'10px 12px',
            background:'rgba(0,0,0,.03)',
            border:'1px solid rgba(0,0,0,.07)',
            borderRadius:10, textAlign:'center'
          }}>
            <div style={{ fontSize:10, fontWeight:900, letterSpacing:'0.12em',
              textTransform:'uppercase', color:'#94a3b8', marginBottom:4 }}>
              Quadrant
            </div>
            <div style={{ fontSize:10, fontWeight:800, color:domColor, lineHeight:1.4 }}>
              {emotion.quadrant?.toUpperCase()}
            </div>
          </div>
        </div>
      )}

      {/* Gauge */}
      <div style={{ width:'100%', maxWidth:260, margin:'0 auto' }}>
        <svg viewBox="0 0 200 105" style={{ width:'100%', height:'auto', display:'block' }}>
          <path d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none" stroke="rgba(0,0,0,0.06)" strokeWidth="14" strokeLinecap="round"/>
          <path d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none" stroke={domColor} strokeWidth="14" strokeLinecap="round"
            strokeDasharray={`${emotion.confidence*251.2} 251.2`}
            style={{ transition:'stroke-dasharray .6s' }}/>
          <g transform={`rotate(${needle},100,100)`}>
            <line x1="100" y1="100" x2="100" y2="32"
              stroke="#0f172a" strokeWidth="2.5" strokeLinecap="round"/>
            <circle cx="100" cy="100" r="5" fill="#0f172a"/>
          </g>
          <text x="14" y="100" fontSize="10" fill="#94a3b8">0%</text>
          <text x="172" y="100" fontSize="10" fill="#94a3b8">100%</text>
        </svg>
      </div>

      {/* Bars — all 7 Ekman including disgust */}
      <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
        {EMOS.map(em => {
          const sc  = scores[em] || 0;
          const col = EMOTION_COLORS[em];
          const active = em === emotion.emotion?.toLowerCase();
          return (
            <div key={em} style={styles.emoRow}>
              <span style={{ ...styles.emoLabel, fontWeight:active?700:400, color:active?'#0f172a':'#94a3b8' }}>
                {EMOTION_ICONS[em]} {em}
              </span>
              <div style={styles.emoTrack}>
                <div style={{
                  ...styles.emoFill,
                  width:`${sc*100}%`, background:col,
                  boxShadow: active ? `0 0 8px ${col}55` : ''
                }}/>
              </div>
              <span style={{ ...styles.emoPct, color:active?col:'#94a3b8' }}>
                {(sc*100).toFixed(0)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
/* ─────────────────────────────────────────
   STYLES
───────────────────────────────────────── */
const styles = {
  root: {
    minHeight: '100vh',
    fontFamily: "'Manrope', sans-serif",
    color: '#2c3437',
    position: 'relative',
    overflowX: 'hidden',
  },
  meshBg: {
    position: 'fixed', inset: 0, zIndex: 0,
    backgroundColor: '#f7f9fb',
    backgroundImage: `
      radial-gradient(at 0% 0%, hsla(210,100%,98%,1) 0, transparent 50%),
      radial-gradient(at 50% 0%, hsla(215,80%,96%,1) 0, transparent 50%),
      radial-gradient(at 100% 0%, hsla(220,70%,94%,1) 0, transparent 50%)
    `,
  },

  // ── Header
  header: {
    position: 'fixed', top: 0, left: 0, right: 0, zIndex: 50,
    background: 'rgba(255,255,255,0.72)',
    backdropFilter: 'blur(14px)',
    WebkitBackdropFilter: 'blur(14px)',
    borderBottom: '1px solid rgba(255,255,255,0.3)',
    boxShadow: '0 1px 20px rgba(0,0,0,0.05)',
  },
  headerInner: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 2rem', height: 64,
    maxWidth: 1440, margin: '0 auto',
  },
  headerLeft: { display:'flex', alignItems:'center', gap:36 },
  logoWrap:   { display:'flex', alignItems:'center', gap:9 },
  logoBox: {
    width: 32, height: 32, borderRadius: 8,
    background: '#0060ad',
    display: 'flex', alignItems:'center', justifyContent:'center',
  },
  logoText: {
    fontSize: 18, fontWeight: 800, letterSpacing: '-0.04em', color: '#0f172a',
  },
  nav: { display: 'flex', gap: 28, alignItems: 'center', height: 64 },
  navItem: {
    background: 'none', border: 'none', cursor: 'pointer',
    fontSize: 14, fontWeight: 600, color: 'rgba(100,116,139,.75)',
    padding: '0 2px', height: '100%',
    display: 'flex', alignItems: 'center',
    borderBottom: '2px solid transparent',
    transition: 'color .2s, border-color .2s',
    fontFamily: "'Manrope', sans-serif",
  },
  navItemActive: {
    color: '#0060ad', borderBottom: '2px solid #0060ad',
  },
  headerRight: { display:'flex', alignItems:'center', gap:14 },
  sessionPill: {
    display: 'flex', alignItems: 'center', gap: 7,
    background: 'rgba(255,255,255,0.5)',
    border: '1px solid rgba(255,255,255,0.7)',
    padding: '6px 14px', borderRadius: 999,
    boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
  },
  sessionDotOuter: {
    position:'relative', width:8, height:8, display:'flex', alignItems:'center', justifyContent:'center',
  },
  sessionDotInner: {
    width: 8, height: 8, borderRadius: '50%', background: '#10b981',
    boxShadow: '0 0 0 3px rgba(16,185,129,.25)',
    animation: 'ping 2s cubic-bezier(0,0,.2,1) infinite',
    display: 'block',
  },
  sessionText: { fontSize: 12, fontWeight: 700, color: '#475569', letterSpacing: '0.04em' },
  iconBtn: {
    position: 'relative',
    width: 38, height: 38, display: 'flex', alignItems:'center', justifyContent:'center',
    background: 'none', border: 'none', cursor: 'pointer',
    color: '#64748b', borderRadius: 10,
    transition: 'background .15s',
  },
  histBadge: {
    position: 'absolute', top: 3, right: 3,
    minWidth: 16, height: 16, padding: '0 4px',
    background: '#0060ad', color: '#fff',
    borderRadius: 999, fontSize: 10, fontWeight: 700,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },

  // ── Main
  main: {
    position: 'relative', zIndex: 1,
    paddingTop: 96, paddingBottom: 80,
    maxWidth: 1440, margin: '0 auto',
    padding: '96px 2rem 80px',
  },

  // ── Hero
  hero: { marginBottom: 44 },
  heroTitle: {
    fontSize: 'clamp(2rem,5vw,3.25rem)', fontWeight: 800,
    letterSpacing: '-0.04em', color: '#0f172a',
    marginBottom: 12, lineHeight: 1.15,
  },
  heroAccent: { color: '#0060ad' },
  heroSub: {
    fontSize: 18, color: '#596064', fontWeight: 300,
    lineHeight: 1.65, maxWidth: 580,
  },

  // ── Mode grid
  modeGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(5,1fr)',
    gap: 14, marginBottom: 44,
  },
  modeCard: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    padding: '28px 16px',
    background: 'rgba(255,255,255,.45)',
    backdropFilter: 'blur(10px)',
    border: '1px solid rgba(255,255,255,.45)',
    borderRadius: 24, cursor: 'pointer',
    transition: 'all .2s ease',
    fontFamily: "'Manrope', sans-serif",
  },
  modeCardActive: {
    background: 'rgba(255,255,255,.95)',
    border: '1px solid rgba(0,96,173,.15)',
    borderBottom: '3.5px solid #0060ad',
    boxShadow: '0 8px 30px rgba(0,96,173,.08)',
  },
  modeLabel: {
    fontSize: 13, fontWeight: 700, letterSpacing: '0.02em',
    color: 'rgba(71,85,105,.7)',
  },
  modeLabelActive: { color: '#0f172a' },

  // ── Workspace
  workspace: {
    display: 'grid', gridTemplateColumns: '1fr 1fr',
    gap: 28, marginBottom: 36,
    alignItems: 'start',
  },

  // ── Cards
  card: {
    display: 'flex', flexDirection: 'column',
    background: 'rgba(255,255,255,.72)',
    backdropFilter: 'blur(12px)',
    WebkitBackdropFilter: 'blur(12px)',
    border: '1px solid rgba(255,255,255,.35)',
    borderRadius: 24,
    boxShadow: '0 20px 50px rgba(0,0,0,.05)',
    minHeight: 500, overflow: 'hidden',
    transition: 'box-shadow .3s',
    userSelect: 'text',
    WebkitUserSelect: 'text',
  },
  cardOutput: {
    display: 'flex', flexDirection: 'column',
    background: 'rgba(255,255,255,.72)',
    backdropFilter: 'blur(12px)',
    WebkitBackdropFilter: 'blur(12px)',
    border: '1px solid rgba(0,96,173,.1)',
    borderRadius: 24,
    boxShadow: '0 20px 50px rgba(0,0,0,.05)',
    minHeight: 500, overflow: 'hidden',
    transition: 'box-shadow .3s',
    userSelect: 'text',
    WebkitUserSelect: 'text',
  },
  cardHeader: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '20px 28px',
    borderBottom: '1px solid rgba(255,255,255,.35)',
  },
  cardHeaderLeft: { display:'flex', alignItems:'center', gap:14 },
  inputBadge: {
    padding: '3px 12px',
    background: 'rgba(15,23,42,.05)',
    borderRadius: 999,
    fontSize: 10, fontWeight: 900, letterSpacing: '0.15em',
    textTransform: 'uppercase', color: '#64748b',
  },
  outputBadge: {
    padding: '3px 12px',
    background: 'rgba(0,96,173,.08)',
    borderRadius: 999,
    fontSize: 10, fontWeight: 900, letterSpacing: '0.15em',
    textTransform: 'uppercase', color: '#0060ad',
  },
  clearBtn: {
    width: 36, height: 36, display:'flex', alignItems:'center', justifyContent:'center',
    background: 'none', border: 'none', cursor: 'pointer',
    color: '#94a3b8', borderRadius: 10,
    transition: 'color .15s, background .15s',
  },
  cardBody: { flex: 1, padding: '32px 28px' },
  cardFooter: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '16px 24px',
    borderTop: '1px solid rgba(0,0,0,.04)',
  },
  footerIconBtn: {
    width: 40, height: 40, display:'flex', alignItems:'center', justifyContent:'center',
    background: 'rgba(255,255,255,.8)',
    border: '1px solid rgba(0,0,0,.08)',
    borderRadius: 12, cursor: 'pointer',
    color: '#64748b', transition: 'all .15s',
  },
  charCount: {
    fontFamily: 'monospace', fontSize: 12, fontWeight: 700,
    color: '#94a3b8', letterSpacing: '0.08em',
  },

  // ── Textarea
  textarea: {
    width: '100%', height: 260,
    background: 'transparent', border: 'none', outline: 'none',
    resize: 'vertical',
    fontSize: 20, fontWeight: 600, color: '#0f172a',
    fontFamily: "'Manrope', sans-serif",
    lineHeight: 1.6,
    userSelect: 'text',
    WebkitUserSelect: 'text',
    MozUserSelect: 'text',
    cursor: 'text',
    pointerEvents: 'auto',
  },

  // ── Output body
  outputBody: {
    flex: 1, padding: '32px 28px', position: 'relative', minHeight: 200,
  },
  shimmerWrap: { display:'flex', flexDirection:'column', gap:14 },
  shimmerLine: {
    width: '88%', height: 22, borderRadius: 999,
    background: 'linear-gradient(90deg,#f0f4f7 25%,#e3e9ed 50%,#f0f4f7 75%)',
    backgroundSize: '200% 100%',
    animation: 'shimmerMove 2s infinite linear',
  },
  translatedText: {
    fontSize: 22, fontWeight: 600, color: '#0f172a',
    lineHeight: 1.65, letterSpacing: '-0.01em',
    wordBreak: 'break-word',
    whiteSpace: 'pre-wrap',
  },
  word: {
    display: 'inline-block',
    animation: 'wordIn .35s ease both',
  },
  caret: {
    display: 'inline-block', width: 2.5, height: '1.1em',
    background: '#0060ad', borderRadius: 2,
    animation: 'blink .85s step-end infinite',
    verticalAlign: 'text-bottom', marginLeft: 2,
  },
  emptyState: {
    height: '100%', display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center',
    gap: 10, minHeight: 180,
    color: '#64748b',
  },
  emotionOverlay: {
    position: 'absolute', bottom: 20, right: 20,
    display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end',
  },
  emotionBadge: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '7px 14px', borderRadius: 16,
    background: 'rgba(212,233,255,.7)',
    backdropFilter: 'blur(8px)',
    border: '1px solid rgba(255,255,255,.5)',
    boxShadow: '0 4px 14px rgba(0,96,173,.06)',
    fontSize: 11, fontWeight: 900, color: '#005490',
    letterSpacing: '0.04em',
  },
  contextBadge: {
    display: 'flex', alignItems: 'center', gap: 5,
    padding: '7px 14px', borderRadius: 16,
    background: 'rgba(216,202,252,.6)',
    backdropFilter: 'blur(8px)',
    border: '1px solid rgba(255,255,255,.5)',
    fontSize: 11, fontWeight: 900, color: '#4b416a',
    letterSpacing: '0.04em',
  },

  // ── Translate button
  translateBtnWrap: {
    padding: '20px 24px',
    background: 'rgba(255,255,255,.25)',
    borderTop: '1px solid rgba(255,255,255,.25)',
  },
  translateBtn: {
    position: 'relative', overflow: 'hidden',
    width: '100%', padding: '18px 24px',
    borderRadius: 16, border: 'none', cursor: 'pointer',
    background: 'linear-gradient(135deg, #0060ad 0%, #599ef1 50%, #0060ad 100%)',
    backgroundSize: '200%',
    color: '#fff', fontFamily: "'Manrope', sans-serif",
    fontSize: 16, fontWeight: 800, letterSpacing: '-0.01em',
    boxShadow: '0 10px 30px rgba(0,96,173,.28)',
    transition: 'all .25s ease',
  },
  translateBtnDisabled: {
    opacity: .45, cursor: 'not-allowed',
    boxShadow: 'none',
  },
  translateBtnInner: {
    position: 'relative', zIndex: 1,
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  translateBtnShine: {
    position: 'absolute', inset: 0,
    background: 'linear-gradient(90deg, transparent, rgba(255,255,255,.18), transparent)',
    transform: 'translateX(-100%)',
    transition: 'transform 1s ease',
  },
  spin: { animation: 'spin 1s linear infinite' },

  // ── Lang select
  langWrap: { position:'relative', display:'flex', alignItems:'center' },
  langSel: {
    appearance: 'none', padding: '7px 32px 7px 14px',
    background: 'rgba(255,255,255,.82)',
    border: '1px solid rgba(0,0,0,.09)',
    borderRadius: 12, cursor: 'pointer', outline: 'none',
    fontSize: 13, fontWeight: 700, color: '#0f172a',
    fontFamily: "'Manrope', sans-serif",
    boxShadow: '0 1px 4px rgba(0,0,0,.05)',
    transition: 'border-color .2s',
  },
  langChev: { position:'absolute', right:10, color:'#94a3b8', pointerEvents:'none' },

  // ── Context toggle
  ctxToggleWrap: { padding: '0 24px 16px' },
  ctxToggle: {
    display: 'flex', alignItems: 'flex-start', gap: 12,
    cursor: 'pointer', padding: '14px 16px',
    background: 'rgba(99,89,131,.05)',
    border: '1px solid rgba(99,89,131,.15)',
    borderRadius: 14,
  },
  toggleTrack: {
    width: 38, height: 22, borderRadius: 11,
    background: '#e2d9f3', border: '1.5px solid rgba(124,58,237,.2)',
    position: 'relative', flexShrink: 0, marginTop: 2,
    transition: 'background .2s',
  },
  toggleTrackOn: { background: 'rgba(124,58,237,.2)', borderColor: '#7c3aed' },
  toggleThumb: {
    position: 'absolute', width: 16, height: 16,
    borderRadius: '50%', background: '#b0a0d8',
    top: 2, left: 2,
    transition: 'transform .22s cubic-bezier(.34,1.4,.64,1), background .2s',
    boxShadow: '0 1px 4px rgba(0,0,0,.12)',
  },
  toggleThumbOn: { transform: 'translateX(16px)', background: '#7c3aed' },
  ctxLabel: { fontSize: 14, fontWeight: 700, color: '#7c3aed' },
  ctxHint:  { fontSize: 11, color: '#9ca3af', marginTop: 3, fontFamily: 'monospace' },

  // ── Context panel
  ctxPanel: {
    margin: '0 24px 16px',
    background: 'rgba(0,0,0,.02)',
    border: '1px solid rgba(0,0,0,.07)',
    borderRadius: 14, padding: '14px 16px',
  },
  ctxPanelHead: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 10,
  },
  ctxPanelTitle: {},
  ctxClearBtn: {
    fontSize: 11, fontWeight: 700, color: '#94a3b8',
    background: 'none', border: 'none', cursor: 'pointer',
  },
  ctxItem: {
    padding: '8px 12px',
    background: 'rgba(124,58,237,.05)',
    borderLeft: '2.5px solid #7c3aed',
    borderRadius: '0 8px 8px 0',
    fontSize: 13, color: '#475569', marginBottom: 6, lineHeight: 1.5,
  },
  ctxItemNum: { fontFamily:'monospace', fontSize:11, fontWeight:700, color:'#7c3aed', marginRight:6 },
  mutedText: { fontSize: 13, color: '#9ca3af', fontStyle: 'italic', lineHeight: 1.5 },

  // ── Transcribed
  transcribed: { padding: '0 24px 16px' },
  transcribedLabel: {
    display: 'block', fontSize: 10, fontWeight: 900, letterSpacing: '0.15em',
    textTransform: 'uppercase', color: '#10b981',
    background: 'rgba(16,185,129,.08)', padding: '4px 10px',
    borderLeft: '2.5px solid #10b981', borderRadius: '0 6px 6px 0',
    marginBottom: 8,
  },
  transcribedText: { fontSize: 14, color: '#475569', lineHeight: 1.65 },

  // ── File zone
  fileZone: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 28px' },
  mediaWrap: { width: '100%', display: 'flex', flexDirection: 'column', gap: 10 },
  mediaTop:  { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  mediaName: { fontFamily:'monospace', fontSize:12, color:'#475569', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:'70%' },
  mediaVideo: { width:'100%', maxHeight:180, borderRadius:10, background:'#000' },
  mediaAudio: { width:'100%', height:40, borderRadius:10 },
  reuploadBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
    width: '100%', padding: '8px', background: 'none',
    border: '1.5px dashed rgba(0,0,0,.12)', borderRadius: 8,
    fontSize: 12, color: '#94a3b8', cursor: 'pointer',
    fontFamily: "'Manrope', sans-serif", fontWeight: 600,
    transition: 'all .2s',
  },
  uploadBtn: {
    width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center',
    padding: '44px 28px', borderRadius: 16, cursor: 'pointer',
    background: 'transparent',
    border: '2px dashed rgba(0,96,173,.25)',
    color: '#0060ad', transition: 'all .25s',
  },
  uploadMain: { fontSize: 15, fontWeight: 700, marginBottom: 4 },
  uploadSub:  { fontSize: 12, opacity: .6, fontFamily: 'monospace' },

  // ── Media output
  mediaOutWrap: {
    margin: '0 24px 0', padding: '14px 16px',
    background: 'rgba(0,96,173,.04)',
    border: '1px solid rgba(0,96,173,.12)',
    borderRadius: 14, display: 'flex', flexDirection: 'column', gap: 8,
  },
  mediaOutHead: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    fontSize: 12, fontWeight: 700, color: '#475569',
  },

  // ── Influence bar
  influenceBar: {
    margin: '0 24px 16px',
    padding: '14px 16px',
    background: 'rgba(124,58,237,.05)',
    border: '1px solid rgba(124,58,237,.15)',
    borderRadius: 14,
  },
  influenceHead: {
    display: 'flex', justifyContent: 'space-between',
    fontSize: 13, fontWeight: 700, color: '#7c3aed', marginBottom: 8,
  },
  influenceTrack: {
    height: 10, background: 'rgba(124,58,237,.1)',
    borderRadius: 5, overflow: 'hidden',
  },
  influenceFill: {
    height: '100%', borderRadius: 5,
    background: 'linear-gradient(90deg,#7c3aed,#a855f7)',
    position: 'relative', overflow: 'hidden',
    transition: 'width .7s ease',
  },
  shimmerFill: {
    position: 'absolute', top: 0, left: '-100%', width: '200%', height: '100%',
    background: 'linear-gradient(90deg,transparent,rgba(255,255,255,.4),transparent)',
    animation: 'shimmerMove 2s infinite',
  },
  influenceNote: {
    fontSize: 11, color: '#9ca3af', marginTop: 6, textAlign: 'right',
    fontFamily: 'monospace',
  },

  // ── Perf card
  perfCard: {
    margin: '0 24px 16px', padding: '14px 16px',
    background: 'rgba(0,96,173,.04)',
    border: '1px solid rgba(0,96,173,.12)',
    borderRadius: 14,
  },
  perfHead: {
    display: 'flex', alignItems: 'center', gap: 6,
    fontSize: 11, fontWeight: 800, textTransform: 'uppercase',
    letterSpacing: '0.07em', color: '#475569', marginBottom: 12,
  },
  perfTitle: {},
  methodBadge: {
    marginLeft: 'auto', padding: '3px 9px', borderRadius: 6,
    fontSize: 10, fontWeight: 800, fontFamily: 'monospace',
  },
  perfGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 },
  perfItem: {
    display: 'flex', justifyContent: 'space-between', padding: '8px 12px',
    background: 'rgba(255,255,255,.75)', borderRadius: 8,
    fontSize: 12, color: '#64748b',
    border: '1px solid rgba(0,0,0,.06)',
  },
  perfTotal: { gridColumn: 'span 2', fontWeight: 700 },

  // ── Emotion card
  emoCard: {
    margin: '0 24px 16px', padding: '18px 16px',
    background: '#fff',
    border: '1px solid rgba(0,0,0,.07)',
    borderRadius: 18, display: 'flex', flexDirection: 'column', gap: 14,
    boxShadow: '0 2px 10px rgba(0,0,0,.04)',
  },
  emoHead:  { display: 'flex', alignItems: 'center', gap: 14 },
  emoName:  { fontFamily: "'Manrope', sans-serif", fontSize: 22, fontWeight: 800, letterSpacing: '-0.03em' },
  emoConf:  { fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'monospace' },
  emoRow:   { display: 'grid', gridTemplateColumns: '110px 1fr 44px', alignItems: 'center', gap: 10 },
  emoLabel: { fontFamily: 'monospace', fontSize: 12, textTransform: 'capitalize', transition: 'color .2s' },
  emoTrack: { height: 14, background: '#f1f5f9', borderRadius: 7, overflow: 'hidden', border: '1px solid rgba(0,0,0,.05)' },
  emoFill:  { height: '100%', borderRadius: 7, transition: 'width .6s ease' },
  emoPct:   { fontFamily: 'monospace', fontSize: 11, fontWeight: 700, textAlign: 'right' },

  // ── History strip
  historyStrip: {
    background: 'rgba(255,255,255,.72)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(255,255,255,.35)',
    borderRadius: 24, padding: '22px 28px',
    marginBottom: 28,
    boxShadow: '0 8px 30px rgba(0,0,0,.05)',
  },
  historyStripHead: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18,
  },
  historyStripTitle: {
    display: 'flex', alignItems: 'center', gap: 8,
    fontSize: 14, fontWeight: 800, color: '#0f172a',
  },
  histCount: {
    fontFamily: 'monospace', fontSize: 11, color: '#94a3b8',
    background: 'rgba(0,0,0,.04)', border: '1px solid rgba(0,0,0,.07)',
    borderRadius: 999, padding: '2px 9px',
  },
  viewAllBtn: {
    fontSize: 12, fontWeight: 700, color: '#0060ad',
    background: 'none', border: 'none', cursor: 'pointer',
  },
  historyGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14,
  },
  histItem: {
    padding: '14px 16px',
    background: 'rgba(0,0,0,.02)',
    border: '1px solid rgba(0,0,0,.07)',
    borderRadius: 16, display: 'flex', flexDirection: 'column', gap: 8,
    animation: 'slideUp .4s ease both',
    transition: 'box-shadow .2s',
  },
  histItemTop: { display:'flex', alignItems:'center', gap:6, flexWrap:'wrap' },
  histLangs:   { fontSize:11, fontWeight:700, color:'#64748b' },
  histTime:    { display:'flex', alignItems:'center', gap:3, marginLeft:'auto', fontSize:11, color:'#94a3b8' },
  histOrig: {
    fontSize: 12, color: '#64748b', lineHeight: 1.45,
    overflow: 'hidden', display: '-webkit-box',
    WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
  },
  histTrans: {
    fontSize: 13, color: '#0f172a', fontWeight: 600, lineHeight: 1.45,
    overflow: 'hidden', display: '-webkit-box',
    WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
  },

  // ── Footer
  footer: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '28px 0 0',
    borderTop: '1px solid rgba(0,0,0,.07)',
    flexWrap: 'wrap', gap: 16,
  },
  footerServices: { display:'flex', flexWrap:'wrap', alignItems:'center', gap:28, opacity:.4 },
  footerService:  { display:'flex', alignItems:'center', gap:8 },
  footerServiceLabel: {
    fontSize: 10, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.18em', color: '#475569',
  },
  footerSession: {
    fontFamily: 'monospace', fontSize: 11, color: '#94a3b8',
  },
  footerSessionText: {},

  // ── Toast
  toast: {
    position: 'fixed', bottom: 28, left: '50%',
    transform: 'translateX(-50%)',
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '14px 28px',
    background: '#0f172a', color: '#fff',
    borderRadius: 24, zIndex: 2000,
    boxShadow: '0 20px 50px rgba(0,0,0,.18)',
    border: '1px solid rgba(255,255,255,.08)',
    animation: 'toastIn .3s ease',
    whiteSpace: 'nowrap',
  },
  toastDot: {
    width: 22, height: 22, borderRadius: '50%',
    background: '#0060ad',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexShrink: 0,
  },
  toastText: { fontSize: 14, fontWeight: 700 },
  toastUndo: {
    marginLeft: 12, fontSize: 10, fontWeight: 900,
    color: '#599ef1', textTransform: 'uppercase', letterSpacing: '0.15em',
    background: 'none', border: 'none', cursor: 'pointer',
  },

  // ── Modal
  overlay: {
    position: 'fixed', inset: 0,
    background: 'rgba(15,23,42,.55)',
    backdropFilter: 'blur(8px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000, padding: '1rem',
    animation: 'fadeIn .2s ease',
  },
  modal: {
    background: '#fff', borderRadius: 24,
    maxWidth: 780, width: '100%', maxHeight: '82vh',
    display: 'flex', flexDirection: 'column',
    boxShadow: '0 30px 80px rgba(0,0,0,.15)',
    border: '1px solid rgba(0,0,0,.07)',
    animation: 'slideUp .28s cubic-bezier(.34,1.4,.64,1)',
    overflow: 'hidden',
  },
  modalHead: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '20px 24px', borderBottom: '1px solid rgba(0,0,0,.07)',
  },
  modalTitle: {
    fontSize: 18, fontWeight: 800, letterSpacing: '-0.03em', color: '#0f172a',
    display: 'flex', alignItems: 'center', gap: 10,
  },
  modalCount: {
    fontFamily: 'monospace', fontSize: 12, fontWeight: 600, color: '#94a3b8',
    background: 'rgba(0,0,0,.04)',
    border: '1px solid rgba(0,0,0,.07)',
    borderRadius: 8, padding: '3px 9px',
  },
  modalBody: { flex: 1, overflowY: 'auto', padding: '20px 24px' },
  histModalItem: {
    padding: '14px 16px',
    background: 'rgba(0,0,0,.02)',
    border: '1px solid rgba(0,0,0,.07)',
    borderLeft: '4px solid #0060ad',
    borderRadius: '0 14px 14px 0',
    marginBottom: 10,
    animation: 'slideUp .3s ease both',
    transition: 'background .15s',
  },
  histModalTop: {
    display: 'flex', alignItems: 'center', gap: 8,
    marginBottom: 8, paddingBottom: 8,
    borderBottom: '1px solid rgba(0,0,0,.06)',
    flexWrap: 'wrap',
  },
  histModalNum:   { fontFamily:'monospace', fontSize:13, fontWeight:700, color:'#0060ad' },
  histLangBadge: {
    fontSize: 12, fontWeight: 600, color: '#475569',
    padding: '2px 9px', background: '#fff',
    border: '1px solid rgba(0,0,0,.08)', borderRadius: 6,
  },
  histOrigText: {
    fontSize: 13, color: '#64748b', lineHeight: 1.55, marginBottom: 4,
  },
  histTransText: {
    fontSize: 13, color: '#0f172a', fontWeight: 600, lineHeight: 1.55,
  },
  emptyHistory: {
    textAlign: 'center', padding: '48px 16px',
  },
};