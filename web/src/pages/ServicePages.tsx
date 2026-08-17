import {
  AlertOctagon,
  ArrowRight,
  BatteryCharging,
  BellRing,
  CalendarCheck,
  CalendarDays,
  Camera,
  Check,
  ChevronRight,
  Clock3,
  FlaskConical,
  ImagePlus,
  Info,
  ListFilter,
  LocateFixed,
  MapPin,
  MapPinned,
  Navigation,
  PackageCheck,
  PackageOpen,
  Recycle,
  Search,
  SlidersHorizontal,
  Star,
  TriangleAlert,
  Truck,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { EmptyState, Field, InlineNotice, PageHeading, SectionHeading, StatusBadge } from '../components/UI'
import { disposalItems, formatDateTime, reportCategories, reportStatuses, serviceLocations } from '../model'
import { useStore } from '../store'

const statusTone = (status: string) => status === 'Resolved' ? 'success' : status === 'Assigned' ? 'warning' : 'info'

export function ReportIssuePage() {
  const { createReport } = useStore()
  const navigate = useNavigate()
  const [category, setCategory] = useState('')
  const [location, setLocation] = useState('')
  const [description, setDescription] = useState('')
  const [observedAt, setObservedAt] = useState(() => new Date().toISOString().slice(0, 16))
  const [hazardous, setHazardous] = useState(false)
  const [files, setFiles] = useState<Array<{ name: string; url: string }>>([])
  const [locationStatus, setLocationStatus] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => () => files.forEach((file) => URL.revokeObjectURL(file.url)), [files])

  const addFiles = (list: FileList | null) => {
    if (!list) return
    const remaining = 3 - files.length
    const next = Array.from(list).slice(0, remaining).map((file) => ({ name: file.name, url: URL.createObjectURL(file) }))
    setFiles((current) => [...current, ...next])
  }

  const removeFile = (name: string) => {
    setFiles((current) => {
      const target = current.find((file) => file.name === name)
      if (target) URL.revokeObjectURL(target.url)
      return current.filter((file) => file.name !== name)
    })
  }

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
    const id = createReport({ category, location, description, observedAt: new Date(observedAt).toISOString(), hazardous, imageNames: files.map((file) => file.name) })
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
          <Field label="Photos" hint={`${files.length}/3 images selected. Images are previewed locally and are not uploaded.`}>
            <label className="file-drop"><ImagePlus /><span><strong>Add up to three photos</strong><small>JPG, PNG or WEBP demonstration files</small></span><input type="file" accept="image/*" multiple onChange={(event) => addFiles(event.target.files)} disabled={files.length >= 3} /></label>
          </Field>
          {files.length > 0 && <div className="image-preview-list">{files.map((file) => <figure key={file.name}><img src={file.url} alt={`Preview of ${file.name}`} /><figcaption>{file.name}</figcaption><button type="button" onClick={() => removeFile(file.name)} aria-label={`Remove ${file.name}`}><X /></button></figure>)}</div>}
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
      <section className="detail-block"><SectionHeading title="Resident description" /><p>{report.description}</p>{report.imageNames.length > 0 && <div className="attachment-chips">{report.imageNames.map((name) => <span key={name}><Camera /> {name}</span>)}</div>}</section>
      <section className="detail-block"><SectionHeading title="Service update" /><div className="service-update"><Truck /><div><strong>{report.status === 'Resolved' ? 'Work marked complete' : report.status === 'Assigned' ? 'Assigned to collection operations' : 'Report is being reviewed'}</strong><p>{report.status === 'Resolved' ? 'This demonstration report has reached its final state.' : 'Updates will appear here and in Notifications as the report progresses.'}</p></div></div></section>
      {report.status !== 'Resolved' && <div className="demo-advance"><FlaskConical /><span><strong>Presentation control</strong><small>Advance this mock report to demonstrate tracking.</small></span><button className="button secondary" type="button" onClick={() => advanceReport(report.id)}>Advance status <ArrowRight /></button></div>}
      {report.status === 'Resolved' && <section className="resolution-actions"><div><h2>Was this issue resolved?</h2><p>Rate the simulated service response or reopen the report.</p></div><div className="star-rating" aria-label="Rate service">{[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" className={(report.rating ?? 0) >= value ? 'active' : ''} onClick={() => { rateReport(report.id, value); setRated(true) }} aria-label={`${value} stars`}><Star /></button>)}</div>{rated && <StatusBadge tone="success">Rating saved</StatusBadge>}<button className="button secondary" type="button" onClick={() => reopenReport(report.id)}>Reopen report</button></section>}
    </div>
  )
}

export function ServicesPage() {
  const services = [
    { to: '/schedule', icon: CalendarDays, label: 'Collection schedule', detail: 'Garbage, recycling and organic pickup dates', meta: 'Next: Wednesday' },
    { to: '/locations', icon: MapPinned, label: 'Drop-off locations', detail: 'Return, recycling, e-waste and hazardous-waste sites', meta: '4 nearby' },
    { to: '/bulky-pickup', icon: Truck, label: 'Bulky-item pickup', detail: 'Book a simulated collection for large household items', meta: 'Booking available' },
    { to: '/guide', icon: Recycle, label: 'Sorting guide', detail: 'Search what belongs in each waste stream', meta: `${disposalItems.length} common items` },
  ]
  return <div className="page-stack"><PageHeading title="Local waste services" description="Collection information, disposal locations and resident service requests." /><div className="service-directory">{services.map(({ to, icon: Icon, label, detail, meta }, index) => <Link key={to} to={to}><span className="service-number">0{index + 1}</span><span className="service-icon"><Icon /></span><span><strong>{label}</strong><small>{detail}</small></span><StatusBadge tone="neutral">{meta}</StatusBadge><ArrowRight /></Link>)}</div><InlineNotice title="Demonstration service area">Dates, locations and bookings are fictional and provided for interface testing only.</InlineNotice></div>
}

export function SchedulePage() {
  const { data, updateSettings } = useStore()
  const collections = [
    { type: 'Garbage', date: 'Wednesday, 19 August', time: 'Before 7:00 AM', tone: 'general' },
    { type: 'Recycling', date: 'Thursday, 20 August', time: 'Earlier service this week', tone: 'recycle' },
    { type: 'Organic', date: 'Saturday, 22 August', time: 'Before 8:00 AM', tone: 'organic' },
  ]
  return <div className="page-stack"><PageHeading title="Collection schedule" description="Demonstration schedule for Jalan Universiti, Petaling Jaya." actions={<button className="button secondary" type="button" onClick={() => updateSettings({ reminders: !data.settings.reminders })}><BellRing /> {data.settings.reminders ? 'Reminders on' : 'Enable reminders'}</button>} /><section className="schedule-lead"><div><span className="eyebrow inverse">Next collection</span><h2>Garbage · Wednesday</h2><p>Set out before 7:00 AM</p></div><strong>02<small>days</small></strong></section><div className="schedule-list">{collections.map((entry, index) => <article key={entry.type}><span className={`schedule-color ${entry.tone}`} /><span><small>0{index + 1}</small><strong>{entry.type}</strong></span><span><strong>{entry.date}</strong><small>{entry.time}</small></span><CalendarCheck /></article>)}</div><InlineNotice tone="warning" title="Temporary service change">Recycling collection starts two hours earlier this Thursday because of scheduled road maintenance.</InlineNotice><section><SectionHeading title="Preparation guidance" /><div className="guidance-grid"><div><Recycle /><strong>Keep recycling clean and dry</strong><p>Loose items should not contain food or liquid.</p></div><div><Clock3 /><strong>Use the correct set-out time</strong><p>Place bins outside no earlier than the evening before.</p></div><div><PackageCheck /><strong>Keep access clear</strong><p>Leave space around bins for safe collection.</p></div></div></section></div>
}

export function SortingGuidePage() {
  const [params] = useSearchParams()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [group, setGroup] = useState('All')
  const groups = ['All', ...Array.from(new Set(disposalItems.map((entry) => entry.group)))]
  const results = disposalItems.filter((entry) => (group === 'All' || entry.group === group) && `${entry.item} ${entry.destination} ${entry.group}`.toLowerCase().includes(query.toLowerCase()))
  return <div className="page-stack"><PageHeading title="What goes where?" description="Search common household items before placing them in a bin or taking them to a facility." /><div className="guide-search"><Search /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search cans, batteries, oil…" aria-label="Search disposal guide" /><span>{results.length} results</span></div><div className="filter-bar guide-filters"><SlidersHorizontal /><span>Material</span>{groups.map((entry) => <button key={entry} className={group === entry ? 'active' : ''} type="button" onClick={() => setGroup(entry)}>{entry}</button>)}</div>{results.length > 0 ? <div className="sorting-results"><div className="table-head"><span>Item</span><span>Where it goes</span><span>Preparation</span><span>Type</span></div>{results.map((entry) => <article key={entry.item}><span className="sorting-icon">{entry.group === 'Hazardous' ? <BatteryCharging /> : <Recycle />}</span><strong>{entry.item}</strong><span>{entry.destination}</span><p>{entry.preparation}</p><StatusBadge tone={entry.group === 'Hazardous' ? 'warning' : 'neutral'}>{entry.group}</StatusBadge></article>)}</div> : <EmptyState icon={<Search />} title="No matching item" detail="Try a broader name or contact the BinSight Assistant for disposal guidance." action={<Link className="button secondary" to="/chat">Ask the assistant</Link>} />}</div>
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
