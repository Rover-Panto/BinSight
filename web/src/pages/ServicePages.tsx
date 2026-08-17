import {
  AlertOctagon,
  ArrowRight,
  BatteryCharging,
  Camera,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Cpu,
  FlaskConical,
  ImagePlus,
  Info,
  ListFilter,
  Leaf,
  LocateFixed,
  MapPin,
  MapPinned,
  Navigation,
  PackageOpen,
  Recycle,
  Search,
  Sofa,
  Star,
  TriangleAlert,
  Trash2,
  Truck,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { EmptyState, Field, InlineNotice, PageHeading, SectionHeading, StatusBadge } from '../components/UI'
import { classifyDisposal, disposalCategories, formatDateTime, reportCategories, reportStatuses, serviceLocations, type ReportAttachment } from '../model'
import { useStore } from '../store'

const statusTone = (status: string) => status === 'Resolved' ? 'success' : status === 'Assigned' ? 'warning' : 'info'
const supportedImageTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])
const maxStoredImageLength = 900_000

const readImageFile = (file: Blob) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Image could not be read.'))
  reader.onerror = () => reject(new Error('Image could not be read.'))
  reader.readAsDataURL(file)
})

const loadImage = (source: string) => new Promise<HTMLImageElement>((resolve, reject) => {
  const image = new Image()
  image.onload = () => resolve(image)
  image.onerror = () => reject(new Error('Image format could not be opened.'))
  image.src = source
})

const renderStoredImage = (image: HTMLImageElement, maxDimension: number, quality: number) => {
  const scale = Math.min(1, maxDimension / Math.max(image.naturalWidth, image.naturalHeight))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Image processing is unavailable in this browser.')
  context.drawImage(image, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/webp', quality)
}

const prepareReportAttachment = async (file: File): Promise<ReportAttachment> => {
  if (!supportedImageTypes.has(file.type)) throw new Error(`${file.name} is not a JPG, PNG or WEBP image.`)
  const source = await readImageFile(file)
  const image = await loadImage(source)
  let dataUrl = renderStoredImage(image, 1400, 0.78)
  if (dataUrl.length > maxStoredImageLength) dataUrl = renderStoredImage(image, 1000, 0.6)
  if (dataUrl.length > maxStoredImageLength) throw new Error(`${file.name} is too large to store safely in this prototype.`)
  const mimeType = dataUrl.slice(5, dataUrl.indexOf(';'))
  return { id: crypto.randomUUID(), name: file.name, mimeType, dataUrl }
}

export function ReportIssuePage() {
  const { createReport } = useStore()
  const navigate = useNavigate()
  const [category, setCategory] = useState('')
  const [location, setLocation] = useState('')
  const [description, setDescription] = useState('')
  const [observedAt, setObservedAt] = useState(() => new Date().toISOString().slice(0, 16))
  const [hazardous, setHazardous] = useState(false)
  const [files, setFiles] = useState<ReportAttachment[]>([])
  const [processingImages, setProcessingImages] = useState(false)
  const [imageError, setImageError] = useState('')
  const [locationStatus, setLocationStatus] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const addFiles = async (list: FileList | null) => {
    if (!list) return
    const remaining = 3 - files.length
    const selected = Array.from(list).slice(0, remaining)
    if (!selected.length) return
    setProcessingImages(true)
    setImageError('')
    const results = await Promise.allSettled(selected.map(prepareReportAttachment))
    const prepared = results.filter((result): result is PromiseFulfilledResult<ReportAttachment> => result.status === 'fulfilled').map((result) => result.value)
    const failure = results.find((result): result is PromiseRejectedResult => result.status === 'rejected')
    if (failure) setImageError(failure.reason instanceof Error ? failure.reason.message : 'One image could not be prepared.')
    if (prepared.length) setFiles((current) => [...current, ...prepared].slice(0, 3))
    setProcessingImages(false)
  }

  const removeFile = (id: string) => setFiles((current) => current.filter((file) => file.id !== id))

  const locate = () => {
    setLocationStatus('Locating…')
    if (!navigator.geolocation) {
      setLocationStatus('Location access is unavailable. Enter an address manually.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocation(`Current location: ${position.coords.latitude.toFixed(4)}, ${position.coords.longitude.toFixed(4)}`)
        setLocationStatus('Current location added.')
      },
      () => setLocationStatus('Permission was not granted. Enter an address manually.'),
      { timeout: 5000 },
    )
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const nextErrors: Record<string, string> = {}
    if (!category) nextErrors.category = 'Choose the type of waste issue.'
    if (location.trim().length < 5) nextErrors.location = 'Enter a clear location.'
    if (description.trim().length < 20) nextErrors.description = 'Add at least 20 characters so the issue can be assessed.'
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    const id = createReport({ category, location, description, observedAt: new Date(observedAt).toISOString(), hazardous, imageNames: files.map((file) => file.name), attachments: files })
    navigate(`/reports/${id}`, { state: { submitted: true } })
  }

  return (
    <div className="page-stack report-form-page">
      <PageHeading eyebrow="Resident service request" title="Report a waste issue" description="Give the local service team enough information to locate and assess the issue." actions={<StatusBadge tone="neutral">Simulated submission</StatusBadge>} />
      {hazardous && <InlineNotice tone="danger" title="Potentially dangerous waste">Do not touch discarded sharps, chemicals or burning material. Move to a safe distance. Use emergency services when there is immediate danger.</InlineNotice>}
      <form className="report-layout" onSubmit={submit} noValidate>
        <div className="report-fields">
          <section className="form-section"><span className="form-step">01</span><div><h2>Issue type</h2><p>Select the closest category.</p></div></section>
          <Field label="Category" error={errors.category}>
            <select value={category} onChange={(event) => { setCategory(event.target.value); setErrors((current) => ({ ...current, category: '' })); if (['Hazardous waste', 'Discarded sharps'].includes(event.target.value)) setHazardous(true) }}>
              <option value="">Choose a category</option>
              {reportCategories.map((option) => <option key={option}>{option}</option>)}
            </select>
          </Field>

          <section className="form-section"><span className="form-step">02</span><div><h2>Location and time</h2><p>Use a recognisable address or landmark.</p></div></section>
          <Field label="Issue location" error={errors.location}>
            <div className="location-field"><MapPin /><input value={location} onChange={(event) => { setLocation(event.target.value); setErrors((current) => ({ ...current, location: '' })) }} placeholder="Street, building or landmark" /><button className="button secondary compact" type="button" onClick={locate}><LocateFixed /> Use current</button></div>
          </Field>
          {locationStatus && <p className="field-status" role="status">{locationStatus}</p>}
          <Field label="When did you observe it?">
            <input type="datetime-local" value={observedAt} onChange={(event) => setObservedAt(event.target.value)} />
          </Field>

          <section className="form-section"><span className="form-step">03</span><div><h2>Evidence and description</h2><p>Add photos only when it is safe.</p></div></section>
          <Field label="Photos" hint={`${files.length}/3 images selected. Compressed copies are kept with this local report.`} error={imageError}>
            <label className="file-drop"><ImagePlus /><span><strong>{processingImages ? 'Preparing images...' : 'Add up to three photos'}</strong><small>JPG, PNG or WEBP demonstration files</small></span><input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => void addFiles(event.target.files)} disabled={files.length >= 3 || processingImages} /></label>
          </Field>
          {files.length > 0 && <div className="image-preview-list">{files.map((file) => <figure key={file.id}><img src={file.dataUrl} alt={`Preview of ${file.name}`} /><figcaption>{file.name}</figcaption><button type="button" onClick={() => removeFile(file.id)} aria-label={`Remove ${file.name}`}><X /></button></figure>)}</div>}
          <Field label="Description" hint={`${description.length}/500 characters`} error={errors.description}>
            <textarea value={description} onChange={(event) => { setDescription(event.target.value.slice(0, 500)); setErrors((current) => ({ ...current, description: '' })) }} placeholder="Describe what happened, where the waste is located and whether access is blocked." rows={6} />
          </Field>
          <label className="hazard-check"><input type="checkbox" checked={hazardous} onChange={(event) => setHazardous(event.target.checked)} /><span><AlertOctagon /><span><strong>This may be dangerous</strong><small>Examples: sharps, chemicals, smoke or material blocking traffic.</small></span></span></label>
          <div className="form-submit-row"><span><Info /> Contact information from the demonstration profile will be attached.</span><button className="button primary" type="submit">Submit report <ArrowRight /></button></div>
        </div>
        <aside className="report-map-panel">
          <span className="eyebrow inverse">Location preview</span>
          <MockMap pins={1} />
          <div><Navigation /><span><strong>{location || 'No location entered'}</strong><small>Static prototype map · verify the written location</small></span></div>
        </aside>
      </form>
    </div>
  )
}

export function ReportsPage() {
  const { data } = useStore()
  const [filter, setFilter] = useState('All')
  const filtered = filter === 'All' ? data.reports : data.reports.filter((report) => report.status === filter)
  return (
    <div className="page-stack">
      <PageHeading title="My reports" description="Track submitted waste issues from acknowledgement to resolution." actions={<Link className="button primary" to="/report"><TriangleAlert /> New report</Link>} />
      <div className="filter-bar"><ListFilter /><span>Filter status</span>{['All', ...reportStatuses].map((status) => <button key={status} className={filter === status ? 'active' : ''} type="button" onClick={() => setFilter(status)}>{status}</button>)}</div>
      {filtered.length > 0 ? <div className="report-table">
        <div className="table-head"><span>Reference</span><span>Issue</span><span>Location</span><span>Status</span><span>Submitted</span><span /></div>
        {filtered.map((report) => <Link key={report.id} to={`/reports/${report.id}`}><strong className="mono">{report.id}</strong><span><strong>{report.category}</strong><small>{report.description}</small></span><span>{report.location}</span><StatusBadge tone={statusTone(report.status)}>{report.status}</StatusBadge><time>{formatDateTime(report.createdAt)}</time><ChevronRight /></Link>)}
      </div> : <EmptyState icon={<PackageOpen />} title="No reports match this filter" detail="Choose a different status or submit a new issue." />}
    </div>
  )
}

export function ReportDetailPage() {
  const { id } = useParams()
  const { data, advanceReport, reopenReport, rateReport } = useStore()
  const report = data.reports.find((entry) => entry.id === id)
  const [rated, setRated] = useState(false)
  if (!report) return <Navigate to="/reports" replace />
  const currentIndex = reportStatuses.indexOf(report.status)
  return (
    <div className="page-stack narrow-page report-detail">
      <PageHeading eyebrow="Waste issue report" title={report.id} description={report.category} actions={<StatusBadge tone={statusTone(report.status)}>{report.status}</StatusBadge>} />
      <section className="report-status-track" aria-label={`Report status: ${report.status}`}>
        {reportStatuses.map((status, index) => <div key={status} className={index <= currentIndex ? 'complete' : ''}><span>{index < currentIndex ? <Check /> : index + 1}</span><strong>{status}</strong><small>{index === 0 ? 'Report recorded' : index === 1 ? 'Details checked' : index === 2 ? 'Crew notified' : 'Issue closed'}</small></div>)}
      </section>
      <section className="report-detail-grid">
        <div><small>Location</small><strong>{report.location}</strong></div><div><small>Observed</small><strong>{formatDateTime(report.observedAt)}</strong></div><div><small>Submitted</small><strong>{formatDateTime(report.createdAt)}</strong></div><div><small>Safety flag</small><strong>{report.hazardous ? 'Potential hazard' : 'No hazard reported'}</strong></div>
      </section>
      <section className="detail-block"><SectionHeading title="Resident description" /><p>{report.description}</p>{report.attachments.length > 0 ? <div className="report-attachment-gallery">{report.attachments.map((attachment) => <figure key={attachment.id}><img src={attachment.dataUrl} alt={`Report attachment ${attachment.name}`} /><figcaption><Camera /> {attachment.name}</figcaption></figure>)}</div> : report.imageNames.length > 0 && <div className="attachment-chips">{report.imageNames.map((name) => <span key={name}><Camera /> {name}</span>)}</div>}</section>
      <section className="detail-block"><SectionHeading title="Service update" /><div className="service-update"><Truck /><div><strong>{report.status === 'Resolved' ? 'Work marked complete' : report.status === 'Assigned' ? 'Assigned to collection operations' : 'Report is being reviewed'}</strong><p>{report.status === 'Resolved' ? 'This demonstration report has reached its final state.' : 'Updates will appear here and in Notifications as the report progresses.'}</p></div></div></section>
      {report.status !== 'Resolved' && <div className="demo-advance"><FlaskConical /><span><strong>Presentation control</strong><small>Advance this mock report to demonstrate tracking.</small></span><button className="button secondary" type="button" onClick={() => advanceReport(report.id)}>Advance status <ArrowRight /></button></div>}
      {report.status === 'Resolved' && <section className="resolution-actions"><div><h2>Was this issue resolved?</h2><p>Rate the simulated service response or reopen the report.</p></div><div className="star-rating" aria-label="Rate service">{[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" className={(report.rating ?? 0) >= value ? 'active' : ''} onClick={() => { rateReport(report.id, value); setRated(true) }} aria-label={`${value} stars`}><Star /></button>)}</div>{rated && <StatusBadge tone="success">Rating saved</StatusBadge>}<button className="button secondary" type="button" onClick={() => reopenReport(report.id)}>Reopen report</button></section>}
    </div>
  )
}

export function ServicesPage() {
  const services = [
    { to: '/locations', icon: MapPinned, label: 'Drop-off locations', detail: 'Return, recycling, e-waste and hazardous-waste sites', meta: '4 nearby' },
    { to: '/bulky-pickup', icon: Truck, label: 'Bulky-item pickup', detail: 'Book a simulated collection for large household items', meta: 'Booking available' },
    { to: '/guide', icon: Recycle, label: 'Disposal helper', detail: 'Match an item to a broad waste stream', meta: '7 waste streams' },
    { to: '/report', icon: TriangleAlert, label: 'Report a waste issue', detail: 'Overflow, illegal dumping, damaged bins or hazards', meta: 'Report online' },
  ]
  return <div className="page-stack"><PageHeading title="Waste services" description="Find a disposal point, arrange a bulky-item pickup or report a local problem." /><div className="service-directory">{services.map(({ to, icon: Icon, label, detail, meta }, index) => <Link key={to} to={to}><span className="service-number">0{index + 1}</span><span className="service-icon"><Icon /></span><span><strong>{label}</strong><small>{detail}</small></span><StatusBadge tone="neutral">{meta}</StatusBadge><ArrowRight /></Link>)}</div><InlineNotice title="Automatic public-bin collection">Sensor readings and route priority determine when public bins are serviced. Residents do not need to follow a fixed timetable.</InlineNotice></div>
}

export function SortingGuidePage() {
  const [params] = useSearchParams()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const match = classifyDisposal(query)
  const selected = query.trim() ? match : disposalCategories.find((category) => category.id === selectedId) ?? null
  const categoryIcon = (id: string) => id === 'hazardous' ? <BatteryCharging /> : id === 'electronics' ? <Cpu /> : id === 'organic' ? <Leaf /> : id === 'bulky' ? <Sofa /> : id === 'general' ? <Trash2 /> : <Recycle />
  const destinationLink = selected?.id === 'returns' ? '/return' : selected?.id === 'bulky' ? '/bulky-pickup' : '/locations'

  return (
    <div className="page-stack disposal-page">
      <PageHeading title="Where should this go?" description="Describe the item in everyday words, or choose the closest waste stream." />
      <div className="disposal-finder">
        <Search />
        <input autoFocus value={query} onChange={(event) => { setQuery(event.target.value); setSelectedId(null) }} placeholder="For example: broken phone" aria-label="Describe an item for disposal guidance" />
        {query && <button className="icon-button" type="button" onClick={() => setQuery('')} aria-label="Clear item description"><X /></button>}
      </div>

      {query.trim() && !match && (
        <section className="uncertain-result" aria-live="polite">
          <span><CircleHelp /></span>
          <div><span className="eyebrow">Needs a closer look</span><h2>We cannot place that item confidently.</h2><p>Choose a broad waste stream below, or ask support before putting it in a public bin.</p></div>
          <Link className="button secondary" to="/chat">Ask BinSight <ArrowRight /></Link>
        </section>
      )}

      {selected && (
        <section className={`disposal-result ${selected.tone}`} aria-live="polite">
          <span className="disposal-result-icon">{categoryIcon(selected.id)}</span>
          <div className="disposal-result-copy"><span className="eyebrow">Best match</span><h2>{selected.title}</h2><p>{selected.examples}</p></div>
          <div className="disposal-destination"><small>Take it to</small><strong>{selected.destination}</strong><p>{selected.guidance}</p></div>
          <Link className="button primary" to={destinationLink}>{selected.id === 'returns' ? 'Start a return' : selected.id === 'bulky' ? 'Book pickup' : 'Find a location'} <ArrowRight /></Link>
        </section>
      )}

      <section>
        <SectionHeading title="Waste streams" detail="Choose the closest category when the item name is uncertain." />
        <div className="disposal-category-grid">
          {disposalCategories.map((category) => (
            <button key={category.id} className={selected?.id === category.id ? 'active' : ''} type="button" onClick={() => { setQuery(''); setSelectedId(category.id) }}>
              <span className={`category-icon ${category.tone}`}>{categoryIcon(category.id)}</span>
              <span><strong>{category.title}</strong><small>{category.destination}</small></span>
              <ChevronRight />
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}

export function LocationsPage() {
  const [sort, setSort] = useState<'distance' | 'name'>('distance')
  const locations = useMemo(() => [...serviceLocations].sort((a, b) => sort === 'distance' ? a.distance - b.distance : a.name.localeCompare(b.name)), [sort])
  return <div className="page-stack"><PageHeading title="Drop-off locations" description="Find a suitable facility for returns, recycling, electronics and hazardous household waste." /><div className="locations-layout"><section className="large-static-map"><MockMap pins={4} />{serviceLocations.map((location, index) => <span key={location.id} className="numbered-pin" style={{ left: `${location.x}%`, top: `${location.y}%` }}>{index + 1}</span>)}<div className="map-legend"><span><i className="map-key blue" /> Return or recycling</span><span><i className="map-key amber" /> Special handling</span></div></section><section><div className="location-sort"><span>{locations.length} demonstration locations</span><label>Sort <select value={sort} onChange={(event) => setSort(event.target.value as 'distance' | 'name')}><option value="distance">Nearest first</option><option value="name">Name</option></select></label></div><div className="location-list">{locations.map((location, index) => <article key={location.id}><span className="location-number">{index + 1}</span><div><StatusBadge tone={location.type === 'Hazardous waste' ? 'warning' : 'info'}>{location.type}</StatusBadge><h2>{location.name}</h2><p>{location.materials}</p><span><Clock3 /> {location.hours}</span></div><strong>{location.distance.toFixed(1)} km</strong><button className="icon-button" type="button" aria-label={`Show ${location.name} on map`}><Navigation /></button></article>)}</div></section></div></div>
}

export function BulkyPickupPage() {
  const [item, setItem] = useState('')
  const [address, setAddress] = useState('Jalan Universiti, Petaling Jaya')
  const [date, setDate] = useState('2026-08-24')
  const [submitted, setSubmitted] = useState(false)
  if (submitted) return <div className="page-stack narrow-page"><PageHeading eyebrow="Booking submitted" title="Pickup request recorded" description="This is a simulated service booking." /><section className="booking-confirmation"><span><Check /></span><h2>BP-3814</h2><p>{item} collection requested for {date} at {address}.</p><Link className="button primary" to="/services">Return to services</Link></section></div>
  return <div className="page-stack narrow-page"><PageHeading title="Bulky-item pickup" description="Request a simulated collection for furniture and large household items." /><InlineNotice tone="warning" title="Check before booking">Construction material, chemicals and commercial waste require a specialist facility and cannot use this service.</InlineNotice><form className="stacked-form bulky-form" onSubmit={(event) => { event.preventDefault(); if (item.trim()) setSubmitted(true) }}><Field label="Item description" hint="Include quantity, approximate size and condition."><textarea required rows={4} value={item} onChange={(event) => setItem(event.target.value)} placeholder="Example: one two-seat fabric sofa" /></Field><Field label="Collection address"><div className="input-with-icon"><MapPin /><input required value={address} onChange={(event) => setAddress(event.target.value)} /></div></Field><Field label="Preferred collection date"><input type="date" required value={date} onChange={(event) => setDate(event.target.value)} /></Field><label className="check-row"><input type="checkbox" required /><span><strong>I can place the item at an accessible collection point</strong><small>Do not block pedestrian, vehicle or emergency access.</small></span></label><button className="button primary" type="submit">Request mock pickup <Truck /></button></form></div>
}

function MockMap({ pins }: { pins: number }) {
  return <div className="map-canvas" aria-label="Static demonstration map"><span className="map-water" /><i className="map-road a" /><i className="map-road b" /><i className="map-road c" /><i className="map-road d" /><span className="map-block one" /><span className="map-block two" /><span className="map-block three" /><span className="map-block four" />{pins === 1 && <span className="single-map-pin"><MapPin /></span>}<span className="map-label label-a">JALAN UNIVERSITI</span><span className="map-label label-b">PERSIARAN BARAT</span></div>
}
