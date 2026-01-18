# Frontend API Integration Guide

Quick reference for integrating Next.js frontends with Machina Client API.

## API Route Pattern

Create API routes in `app/api/` that proxy to Machina Client API:

```typescript
// app/api/documents/route.ts
import { NextRequest, NextResponse } from "next/server"

export async function GET(req: NextRequest) {
  const api_url = process.env.MACHINA_CLIENT_URL
  const bearer = process.env.MACHINA_API_KEY

  const headers = {
    "X-Api-Token": `${bearer}`,
    "Content-Type": "application/json",
  }

  const response = await fetch(`${api_url}/document/search`, {
    method: "POST",
    headers,
    body: JSON.stringify({ filters: { name: "my-document" } })
  })

  const payload = await response.json()
  return NextResponse.json({ status: true, data: payload.data })
}
```

## Document Search

### Basic Search

```typescript
const body = {
  filters: { name: "ros-output" },  // Required: document name
  page: 1,
  page_size: 50
}
```

### Sorters

**Format**: `["field", direction]` where direction is `1` (asc) or `-1` (desc)

```typescript
// Correct
sorters: ["created", -1]  // Most recent first

// Wrong - causes 500 error
sorters: [["created", -1]]
```

### Multiple Filters with $and

Combine multiple conditions:

```typescript
const filters: any = { name: "ros-output" }
const andConditions: any[] = []

if (competition) {
  andConditions.push({
    "$or": [
      { "metadata.competition": { $regex: competition, $options: 'i' } },
      { "value.match.competition": { $regex: competition, $options: 'i' } }
    ]
  })
}

if (startDate) {
  andConditions.push({ created: { $gte: startDate } })
}

if (andConditions.length > 0) {
  filters["$and"] = andConditions
}
```

### Text Search

Search across multiple fields:

```typescript
if (search) {
  andConditions.push({
    "$or": [
      { "metadata.match_title": { $regex: search, $options: 'i' } },
      { "metadata.event_code": { $regex: search, $options: 'i' } },
      { "value.title": { $regex: search, $options: 'i' } }
    ]
  })
}
```

## Document Structure

Documents have standard fields:

```typescript
interface Document {
  _id: string           // MongoDB ObjectId
  name: string          // Document type identifier
  created: string       // ISO date (use for sorting)
  updated: string       // ISO date
  metadata: {           // Indexed, searchable fields
    event_code?: string
    competition?: string
    // ... custom fields
  }
  value: {              // Main document content
    title?: string
    spreadsheet_url?: string  // GCS file URLs
    csv_url?: string
    // ... custom data
  }
}
```

**Key points**:
- Use `metadata` for fields you need to filter/search
- Use `value` for the main document payload
- `created`/`updated` are auto-managed by the API
- Files (xlsx, csv) are stored in GCS, URLs in `value`

## File Downloads

Fetch files from GCS URLs stored in documents:

```typescript
// Get document
const doc = await fetchDocument(id)
const fileUrl = doc.value?.spreadsheet_url

if (!fileUrl) {
  return NextResponse.json({ error: "File not available" }, { status: 404 })
}

// Proxy the file
const fileResponse = await fetch(fileUrl)
const buffer = await fileResponse.arrayBuffer()

return new NextResponse(buffer, {
  headers: {
    'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'Content-Disposition': `attachment; filename="${filename}"`,
  }
})
```

## Common Patterns

### Debounced Search Input

```typescript
const [localSearch, setLocalSearch] = useState(filters.search)

useEffect(() => {
  const timer = setTimeout(() => {
    if (localSearch !== filters.search) {
      onFilterChange({ ...filters, search: localSearch })
    }
  }, 300)
  return () => clearTimeout(timer)
}, [localSearch])
```

### Loading States

```typescript
const fetchData = useCallback(async () => {
  setLoading(true)
  try {
    const response = await fetch(`/api/endpoint?${params}`)
    const result = await response.json()
    if (result.status && result.data) {
      setData(result.data)
    }
  } finally {
    setLoading(false)
  }
}, [dependencies])  // Include all filter/sort dependencies
```

### Availability Checks

Check if optional resources exist before showing actions:

```typescript
const hasXlsx = !!output.value?.spreadsheet_url
const hasCsv = !!output.value?.csv_url

<Button disabled={!hasXlsx}>
  Download Excel {!hasXlsx && '(unavailable)'}
</Button>
```

## Environment Variables

```env
MACHINA_CLIENT_URL=http://localhost:31000
MACHINA_API_KEY=your-api-key
```

## Quick Reference

| Operation | Endpoint | Method |
|-----------|----------|--------|
| Search documents | `/document/search` | POST |
| Get by ID | `/document/{id}` | GET |
| Create | `/document` | POST |
| Update | `/document/{id}` | PUT |
| Delete | `/document/{id}` | DELETE |
| Execute agent | `/agent/{id}/execute` | POST |
| Execute workflow | `/workflow/execute` | POST |
