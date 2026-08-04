import { useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import {
  ArrowLeft,
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Download,
  Grid2X2,
  Image as ImageIcon,
  LayoutPanelLeft,
  Lock,
  Maximize2,
  MessageCircle,
  Minus,
  MousePointer2,
  Redo2,
  Save,
  Sparkles,
  Type,
  Undo2,
  Unlock,
  Users,
  WandSparkles,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import type { BubbleEdit, EpisodeEdit, MangaResult, PanelEdit } from './App'
import './MangaCanvas.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
type Tool = 'select' | 'pages' | 'layouts' | 'art' | 'bubbles' | 'text' | 'characters'

const tools: { id: Tool; label: string; icon: typeof MousePointer2 }[] = [
  { id: 'select', label: 'Chọn', icon: MousePointer2 },
  { id: 'pages', label: 'Trang', icon: BookOpen },
  { id: 'layouts', label: 'Bố cục', icon: Grid2X2 },
  { id: 'art', label: 'Tranh', icon: ImageIcon },
  { id: 'bubbles', label: 'Bong bóng', icon: MessageCircle },
  { id: 'text', label: 'Chữ', icon: Type },
  { id: 'characters', label: 'Nhân vật', icon: Users },
]

const bubbleNames: Record<BubbleEdit['bubble_type'], string> = {
  speech: 'Hội thoại', thought: 'Suy nghĩ', whisper: 'Thì thầm', shout: 'La hét', caption: 'Dẫn truyện', sfx: 'Hiệu ứng',
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function layoutBoxes(count: number, variant: number) {
  const gap = .024
  if (variant === 1 && count >= 3) {
    const detailCount = count - 1
    const rows = Math.ceil(detailCount / 2)
    const detailHeight = (.5 - gap * (rows - 1)) / rows
    return Array.from({ length: count }, (_, index) => index === 0
      ? { x: .035, y: .025, width: .93, height: .4 }
      : { x: index % 2 ? .51 : .035, y: .45 + Math.floor((index - 1) / 2) * (detailHeight + gap), width: index % 2 ? .455 : .445, height: detailHeight })
  }
  if (variant === 2) {
    const height = (.95 - gap * (count - 1)) / count
    return Array.from({ length: count }, (_, index) => ({ x: .035, y: .025 + index * (height + gap), width: .93, height }))
  }
  const columns = count > 4 ? 3 : 2
  const rows = Math.ceil(count / columns)
  const width = (.93 - gap * (columns - 1)) / columns
  const height = (.95 - gap * (rows - 1)) / rows
  return Array.from({ length: count }, (_, index) => ({ x: .035 + (columns - 1 - index % columns) * (width + gap), y: .025 + Math.floor(index / columns) * (height + gap), width, height }))
}

export function MangaCanvas({ result, episode, page, onPage, onEpisode, onExit, onArtwork }: {
  result: MangaResult
  episode: EpisodeEdit
  page: number
  onPage: (page: number) => void
  onEpisode: (episode: EpisodeEdit) => void
  onExit: () => void
  onArtwork: () => void
}) {
  const [tool, setTool] = useState<Tool>('pages')
  const [activePanelId, setActivePanelId] = useState('')
  const [activeBubbleId, setActiveBubbleId] = useState<string | null>(null)
  const [zoom, setZoom] = useState(72)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [rendering, setRendering] = useState(false)
  const [promptSaving, setPromptSaving] = useState(false)
  const [approvalError, setApprovalError] = useState('')
  const [promptDraft, setPromptDraft] = useState({ positive_prompt: '', negative_prompt: '', composition_control: '', identity_mode: 'auto' as 'auto' | 'reference' | 'off', identity_strength: null as number | null })
  const drag = useRef<{ id: string; panelId: string; startX: number; startY: number; x: number; y: number; width: number; height: number } | null>(null)
  const history = useRef<EpisodeEdit[]>([])
  const future = useRef<EpisodeEdit[]>([])

  const storyPage = result.story.pages.find((item) => item.page_number === page) || result.story.pages[0]
  const editPage = episode.editor.pages.find((item) => item.page_number === storyPage.page_number) || episode.editor.pages[0]
  const activePanel = editPage.panels.find((item) => item.panel_id === activePanelId) || editPage.panels[0]
  const activeBubble = activePanel?.bubbles.find((item) => item.bubble_id === activeBubbleId) || null
  const activePrompt = (episode.generation || result.generation).panels.find((item) => item.panel_id === activePanel?.panel_id)
  const quality = episode.critique
  const panelQuality = quality?.panel_critiques.find((item) => item.panel_id === activePanel?.panel_id)
  const rendered = useMemo(() => new Map((episode.render || result.render).panels.map((item) => [item.panel_id, item])), [episode.render, result.render])

  useEffect(() => {
    if (!activePrompt) return
    setPromptDraft({
      positive_prompt: activePrompt.positive_prompt,
      negative_prompt: activePrompt.negative_prompt,
      composition_control: activePrompt.composition_control,
      identity_mode: activePrompt.identity_mode || 'auto',
      identity_strength: activePrompt.identity_strength ?? null,
    })
  }, [activePrompt])

  const applyEpisode = (next: EpisodeEdit) => {
    history.current.push(episode)
    future.current = []
    onEpisode(next)
    setSaveState('idle')
  }
  const undo = () => {
    const previous = history.current.pop()
    if (!previous) return
    future.current.push(episode)
    onEpisode(previous)
    setSaveState('idle')
  }
  const redo = () => {
    const next = future.current.pop()
    if (!next) return
    history.current.push(episode)
    onEpisode(next)
    setSaveState('idle')
  }
  const commitPanel = (panelId: string, change: (panel: PanelEdit) => PanelEdit) => {
    applyEpisode({ ...episode, editor: { ...episode.editor, pages: episode.editor.pages.map((item) => item.page_number !== editPage.page_number ? item : { ...item, panels: item.panels.map((panel) => panel.panel_id === panelId ? change(panel) : panel) }) } })
  }
  const updateActivePanel = (change: (panel: PanelEdit) => PanelEdit) => activePanel && commitPanel(activePanel.panel_id, change)
  const updateBubble = (bubbleId: string, change: (bubble: BubbleEdit) => BubbleEdit) => updateActivePanel((panel) => ({ ...panel, bubbles: panel.bubbles.map((bubble) => bubble.bubble_id === bubbleId ? change(bubble) : bubble) }))

  const selectPanel = (panelId: string) => { setActivePanelId(panelId); setActiveBubbleId(null); setTool('select') }
  const selectBubble = (event: ReactPointerEvent, panelId: string, bubbleId: string) => {
    event.stopPropagation(); setActivePanelId(panelId); setActiveBubbleId(bubbleId); setTool('bubbles')
  }
  const startBubbleDrag = (event: ReactPointerEvent<HTMLElement>, panelId: string, bubble: BubbleEdit) => {
    event.stopPropagation()
    const panelElement = event.currentTarget.parentElement
    if (!panelElement || bubble.locked) return
    event.currentTarget.setPointerCapture(event.pointerId)
    const rect = panelElement.getBoundingClientRect()
    drag.current = { id: bubble.bubble_id, panelId, startX: event.clientX, startY: event.clientY, x: bubble.box.x, y: bubble.box.y, width: rect.width, height: rect.height }
    setActivePanelId(panelId); setActiveBubbleId(bubble.bubble_id); setTool('bubbles')
  }
  const moveBubble = (event: ReactPointerEvent<HTMLElement>, bubble: BubbleEdit) => {
    const current = drag.current
    if (!current || current.id !== bubble.bubble_id) return
    const x = clamp(current.x + (event.clientX - current.startX) / current.width, 0, 1 - bubble.box.width)
    const y = clamp(current.y + (event.clientY - current.startY) / current.height, 0, 1 - bubble.box.height)
    commitPanel(current.panelId, (panel) => ({ ...panel, bubbles: panel.bubbles.map((item) => item.bubble_id === bubble.bubble_id ? { ...item, box: { ...item.box, x, y } } : item) }))
  }
  const addBubble = (type: BubbleEdit['bubble_type'] = 'speech') => {
    if (!activePanel) return
    const id = `${activePanel.panel_id}_${type}_${Date.now()}`
    updateActivePanel((panel) => ({ ...panel, bubbles: [...panel.bubbles, { bubble_id: id, text: type === 'sfx' ? 'BÙM!' : 'Nhập lời thoại…', delivery: 'normal', bubble_type: type, box: { x: .62, y: .08, width: .3, height: .15 }, reading_order: panel.bubbles.length + 1, locked: false }] }))
    setActiveBubbleId(id); setTool('bubbles')
  }
  const applyLayout = (variant: number) => {
    const boxes = layoutBoxes(editPage.panels.length, variant)
    applyEpisode({ ...episode, editor: { ...episode.editor, pages: episode.editor.pages.map((item) => item.page_number !== editPage.page_number ? item : { ...item, panels: item.panels.map((panel, index) => ({ ...panel, box: boxes[index] })) }) } })
  }
  const save = async () => {
    if (!result.episode_id) { setSaveState('saved'); return }
    setSaveState('saving')
    try {
      const response = await fetch(`${API_BASE}/story-episodes/${result.episode_id}/editor`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: episode.revision, pages: episode.editor.pages, status: episode.status }) })
      if (!response.ok) throw new Error()
      onEpisode(await response.json()); setSaveState('saved')
    } catch { setSaveState('error') }
  }
  const rerenderPanel = async () => {
    if (!result.episode_id || !activePanel) return
    setRendering(true)
    try {
      const response = await fetch(`${API_BASE}/story-episodes/${result.episode_id}/rerender`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: episode.revision, mode: 'comfyui', panel_ids: [activePanel.panel_id] }) })
      if (!response.ok) throw new Error()
      onEpisode(await response.json())
      setApprovalError('')
    } finally { setRendering(false) }
  }
  const savePrompt = async () => {
    if (!result.episode_id || !activePanel) return
    setPromptSaving(true); setApprovalError('')
    try {
      const response = await fetch(`${API_BASE}/story-episodes/${result.episode_id}/generation/panels/${activePanel.panel_id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: episode.revision, ...promptDraft }) })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Không lưu được prompt')
      onEpisode(payload)
    } catch (error) { setApprovalError(error instanceof Error ? error.message : 'Không lưu được prompt') }
    finally { setPromptSaving(false) }
  }
  const approveEpisode = async () => {
    if (!result.episode_id) return
    setApprovalError('')
    try {
      const response = await fetch(`${API_BASE}/story-episodes/${result.episode_id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: episode.revision }) })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Chưa thể duyệt xuất bản')
      onEpisode(payload); onArtwork()
    } catch (error) { setApprovalError(error instanceof Error ? error.message : 'Chưa thể duyệt xuất bản') }
  }

  return <div className="manga-editor-shell">
    <header className="manga-editor-topbar">
      <div className="editor-project"><button onClick={onExit} aria-label="Quay lại"><ArrowLeft /></button><span className="editor-logo">漫</span><div><strong>{result.story.title}</strong><small>Tập {result.episode_number || 1} · {saveState === 'idle' ? 'Có thay đổi chưa lưu' : saveState === 'saving' ? 'Đang lưu…' : saveState === 'saved' ? 'Đã lưu' : 'Lưu thất bại'}</small></div><ChevronDown /></div>
      <div className="history-actions"><button aria-label="Hoàn tác" onClick={undo} disabled={!history.current.length}><Undo2 /></button><button aria-label="Làm lại" onClick={redo} disabled={!future.current.length}><Redo2 /></button><span /></div>
      <div className="editor-publish"><span className="editor-hint"><CircleHelp /> {quality ? `Quality ${quality.overall_score.toFixed(1)}/10` : 'Cần review mới sau khi dựng'}</span><button className="save-canvas" onClick={() => void save()} disabled={saveState === 'saving'}><Save /> Lưu</button><button className="publish-button" onClick={() => episode.status === 'approved' ? onArtwork() : void approveEpisode()}><Sparkles /> {episode.status === 'approved' ? 'Mở bản xuất' : 'Duyệt & xuất bản'}</button></div>
    </header>

    <div className="manga-editor-body">
      <aside className="editor-toolrail">{tools.map(({ id, label, icon: Icon }) => <button key={id} className={tool === id ? 'active' : ''} onClick={() => setTool(id)} title={label}><Icon /><span>{label}</span></button>)}</aside>
      <aside className="asset-drawer">
        <div className="drawer-heading"><div><small>WORKSPACE</small><h2>{tools.find((item) => item.id === tool)?.label}</h2></div><button><Minus /></button></div>
        {tool === 'pages' && <><div className="drawer-action-row"><strong>{result.story.pages.length} trang</strong></div><div className="page-thumb-list">{result.story.pages.map((item) => <button key={item.page_number} className={item.page_number === storyPage.page_number ? 'active' : ''} onClick={() => onPage(item.page_number)}><span className="page-thumb"><i>{item.panels.map((panel) => <b key={panel.panel_id} />)}</i></span><span><strong>Trang {item.page_number}</strong><small>{item.panels.length} panel</small></span></button>)}</div></>}
        {tool === 'layouts' && <><p className="drawer-copy">Chọn bố cục manga chuyên nghiệp. Nội dung panel và thoại được giữ nguyên.</p><div className="layout-presets">{[0, 1, 2].map((variant) => <button key={variant} onClick={() => applyLayout(variant)}><span className={`layout-mini variant-${variant}`}>{Array.from({ length: Math.min(editPage.panels.length, 6) }, (_, index) => <i key={index} />)}</span><strong>{['Lưới cân bằng', 'Hero mở đầu', 'Nhịp điện ảnh'][variant]}</strong></button>)}</div></>}
        {tool === 'bubbles' && <><p className="drawer-copy">Thêm bong bóng rồi kéo trực tiếp trên trang để đặt vị trí.</p><div className="bubble-palette">{(['speech', 'thought', 'whisper', 'shout', 'caption', 'sfx'] as BubbleEdit['bubble_type'][]).map((type) => <button key={type} onClick={() => addBubble(type)}><i className={type}>Aa</i><span>{bubbleNames[type]}</span></button>)}</div></>}
        {tool === 'characters' && <div className="canvas-character-list">{result.story.characters.map((character, index) => <article key={character.name}><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{character.name}</strong><small>{character.role}</small><p>{character.appearance}</p></div><i><Check /></i></article>)}</div>}
        {tool === 'art' && <><button className="generate-panel-card" onClick={() => void rerenderPanel()} disabled={rendering}><WandSparkles /><strong>{rendering ? 'Đang dựng panel…' : 'Dựng lại panel đã chọn'}</strong><small>Animagine XL · giữ identity seed</small></button><div className="art-source"><span><ImageIcon /></span><div><strong>AI Artwork</strong><small>{activePanel?.panel_id}</small></div></div></>}
        {tool === 'text' && <div className="typography-library"><button><b>AA</b><span><strong>Manga Sans</strong><small>Hội thoại</small></span></button><button><b className="serif">Aa</b><span><strong>Editorial Serif</strong><small>Dẫn truyện</small></span></button><button><b className="impact">BÙM</b><span><strong>Impact SFX</strong><small>Hiệu ứng</small></span></button></div>}
        {tool === 'select' && <div className="selection-help"><MousePointer2 /><h3>Chọn trực tiếp trên trang</h3><p>Chọn panel để sửa khung, chọn bong bóng để sửa chữ hoặc kéo vị trí.</p></div>}
      </aside>

      <main className="canvas-stage">
        <div className="canvas-breadcrumb"><span>TRANG {storyPage.page_number}</span><i /> <span>ĐỌC PHẢI → TRÁI</span></div>
        <div className="canvas-scroll">
          <div className="production-page" style={{ width: `${zoom}%` }}>
            {editPage.panels.map((panel) => {
              const storyPanel = storyPage.panels.find((item) => item.panel_id === panel.panel_id)
              const art = rendered.get(panel.panel_id)
              return <div key={panel.panel_id} className={`canvas-panel ${activePanel?.panel_id === panel.panel_id ? 'selected' : ''}`} onPointerDown={() => selectPanel(panel.panel_id)} style={{ left: `${panel.box.x * 100}%`, top: `${panel.box.y * 100}%`, width: `${panel.box.width * 100}%`, height: `${panel.box.height * 100}%` }}>
                {art?.image_url ? <img src={`${API_BASE}${art.image_url}`} alt={storyPanel?.action || panel.panel_id} draggable={false} /> : <div className="panel-placeholder"><ImageIcon /><span>{storyPanel?.action}</span></div>}
                <span className="panel-order">{panel.reading_order}</span>
                {panel.artwork_locked && <span className="panel-lock"><Lock /></span>}
                {panel.bubbles.map((bubble) => <span key={bubble.bubble_id} className={`canvas-bubble ${bubble.bubble_type} ${activeBubble?.bubble_id === bubble.bubble_id ? 'selected' : ''}`} style={{ left: `${bubble.box.x * 100}%`, top: `${bubble.box.y * 100}%`, width: `${bubble.box.width * 100}%`, minHeight: `${bubble.box.height * 100}%` }} onPointerDown={(event) => { selectBubble(event, panel.panel_id, bubble.bubble_id); startBubbleDrag(event, panel.panel_id, bubble) }} onPointerMove={(event) => moveBubble(event, bubble)} onPointerUp={() => { drag.current = null }}><i>{bubble.text}</i></span>)}
              </div>
            })}
          </div>
        </div>
        <div className="canvas-footer"><div><button onClick={() => onPage(Math.max(1, storyPage.page_number - 1))}><ChevronLeft /></button><span>Trang {storyPage.page_number} / {result.story.pages.length}</span><button onClick={() => onPage(Math.min(result.story.pages.length, storyPage.page_number + 1))}><ChevronRight /></button></div><div className="zoom-control"><button onClick={() => setZoom(clamp(zoom - 8, 40, 100))}><ZoomOut /></button><input type="range" min="40" max="100" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} /><span>{zoom}%</span><button onClick={() => setZoom(clamp(zoom + 8, 40, 100))}><ZoomIn /></button><button onClick={() => setZoom(72)}><Maximize2 /></button></div></div>
      </main>

      <aside className="property-inspector">
        <div className="inspector-head"><div><small>INSPECTOR</small><h2>{activeBubble ? 'Bong bóng thoại' : 'Thuộc tính panel'}</h2></div>{activePanel && <button onClick={() => updateActivePanel((panel) => ({ ...panel, panel_locked: !panel.panel_locked }))}>{activePanel.panel_locked ? <Lock /> : <Unlock />}</button>}</div>
        {activeBubble ? <div className="inspector-content">
          <label><span>Nội dung</span><textarea value={activeBubble.text} onChange={(event) => updateBubble(activeBubble.bubble_id, (bubble) => ({ ...bubble, text: event.target.value }))} /></label>
          <div className="inspector-grid"><label><span>Kiểu</span><select value={activeBubble.bubble_type} onChange={(event) => updateBubble(activeBubble.bubble_id, (bubble) => ({ ...bubble, bubble_type: event.target.value as BubbleEdit['bubble_type'] }))}>{Object.entries(bubbleNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label><span>Người nói</span><input value={activeBubble.speaker || ''} onChange={(event) => updateBubble(activeBubble.bubble_id, (bubble) => ({ ...bubble, speaker: event.target.value }))} /></label></div>
          <PropertySliders box={activeBubble.box} onChange={(key, value) => updateBubble(activeBubble.bubble_id, (bubble) => ({ ...bubble, box: { ...bubble.box, [key]: value } }))} />
          <button className="delete-layer" onClick={() => { updateActivePanel((panel) => ({ ...panel, bubbles: panel.bubbles.filter((bubble) => bubble.bubble_id !== activeBubble.bubble_id) })); setActiveBubbleId(null) }}>Xóa bong bóng</button>
        </div> : activePanel ? <div className="inspector-content">
          {approvalError && <div className="canvas-inline-error">{approvalError}</div>}
          <div className="selected-panel-card"><span>{activePanel.reading_order}</span><div><strong>{activePanel.panel_id}</strong><small>{storyPage.panels.find((item) => item.panel_id === activePanel.panel_id)?.shot_type.replaceAll('_', ' ')}</small></div></div>
          {panelQuality && <div className={`panel-quality ${panelQuality.score >= 7 ? 'pass' : 'fail'}`}><strong>{panelQuality.score.toFixed(1)}</strong><span>{panelQuality.score >= 7 ? 'Sẵn sàng để duyệt' : 'Cần dựng lại'}<small>{panelQuality.issues.join(' · ') || panelQuality.strengths.join(' · ')}</small></span></div>}
          {activePrompt && <div className="prompt-editor"><div className="property-title"><span>Prompt sản xuất</span><WandSparkles /></div><label><span>Positive prompt</span><textarea value={promptDraft.positive_prompt} onChange={(event) => setPromptDraft((current) => ({ ...current, positive_prompt: event.target.value }))} /></label><label><span>Bố cục</span><textarea className="compact" value={promptDraft.composition_control} onChange={(event) => setPromptDraft((current) => ({ ...current, composition_control: event.target.value }))} /></label><div className="identity-controls"><label><span>Identity reference</span><select value={promptDraft.identity_mode} onChange={(event) => setPromptDraft((current) => ({ ...current, identity_mode: event.target.value as 'auto' | 'reference' | 'off' }))}><option value="auto">Tự động theo cảnh</option><option value="reference">Luôn khóa nhân vật</option><option value="off">Tắt cho panel này</option></select></label><label><span>Strength override</span><input type="number" min="0" max="1.5" step="0.05" placeholder="Auto" value={promptDraft.identity_strength ?? ''} onChange={(event) => setPromptDraft((current) => ({ ...current, identity_strength: event.target.value === '' ? null : Number(event.target.value) }))} /></label></div><details><summary>Negative prompt</summary><textarea value={promptDraft.negative_prompt} onChange={(event) => setPromptDraft((current) => ({ ...current, negative_prompt: event.target.value }))} /></details><button onClick={() => void savePrompt()} disabled={promptSaving}>{promptSaving ? 'Đang lưu…' : 'Lưu prompt trước khi dựng'}</button></div>}
          <PropertySliders box={activePanel.box} onChange={(key, value) => updateActivePanel((panel) => ({ ...panel, box: { ...panel.box, [key]: value } }))} />
          <label className="switch-row"><span><strong>Khóa tranh</strong><small>Không render lại ngoài ý muốn</small></span><input type="checkbox" checked={activePanel.artwork_locked} onChange={(event) => updateActivePanel((panel) => ({ ...panel, artwork_locked: event.target.checked }))} /></label>
          <div className="panel-story-info"><span>NỘI DUNG PANEL</span><p>{storyPage.panels.find((item) => item.panel_id === activePanel.panel_id)?.action}</p></div>
          <button className="inspector-generate" onClick={() => void rerenderPanel()} disabled={rendering || activePanel.artwork_locked}><WandSparkles /> {rendering ? 'Animagine đang dựng…' : 'Dựng lại panel này'}</button>
        </div> : <div className="selection-help"><LayoutPanelLeft /><h3>Chưa chọn panel</h3><p>Nhấp một panel trên trang để xem thuộc tính.</p></div>}
        <footer className="inspector-footer"><button onClick={onArtwork}><Download /> Xem bản xuất</button></footer>
      </aside>
    </div>
  </div>
}

function PropertySliders({ box, onChange }: { box: { x: number; y: number; width: number; height: number }; onChange: (key: 'x' | 'y' | 'width' | 'height', value: number) => void }) {
  const limits = (key: 'x' | 'y' | 'width' | 'height') => ({
    min: key === 'width' || key === 'height' ? .05 : 0,
    max: key === 'x' ? 1 - box.width : key === 'y' ? 1 - box.height : key === 'width' ? 1 - box.x : 1 - box.y,
  })
  return <div className="property-section"><div className="property-title"><span>Vị trí & kích thước</span><Maximize2 /></div>{(['x', 'y', 'width', 'height'] as const).map((key) => <label className="property-slider" key={key}><span>{key === 'width' ? 'Rộng' : key === 'height' ? 'Cao' : key.toUpperCase()}</span><input type="range" min={limits(key).min} max={limits(key).max} step="0.01" value={box[key]} onChange={(event) => onChange(key, clamp(Number(event.target.value), limits(key).min, limits(key).max))} /><output>{Math.round(box[key] * 100)}%</output></label>)}</div>
}
