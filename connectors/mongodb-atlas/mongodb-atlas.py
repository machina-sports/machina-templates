"""
MongoDB Atlas Connector

Provides read/write operations against MongoDB Atlas for shared data caching
across multiple tenants. Supports TTL-based auto-expiry, upserts, and flexible
queries.

All functions receive request_data with:
  - headers.connection_string: MongoDB Atlas connection string
  - headers.database: Database name (default: "machina_cache")
  - params.*: Operation-specific parameters

Commands:
  - write_document: Upsert a single document
  - write_many: Upsert multiple documents in bulk
  - read_document: Read a single document by _id
  - lookup: Query documents with filters
  - search_cache: Query the search cache (returns answer + search_results format)
  - delete_document: Delete a single document by _id
  - delete_many: Delete documents matching a filter
"""

import json
import datetime


def _get_collection(headers, params):
    """Get a MongoDB collection from connection parameters."""
    from pymongo import MongoClient

    connection_string = headers.get("connection_string", "")
    database = headers.get("database", "machina_cache")
    collection = params.get("collection", "")

    if not connection_string:
        raise ValueError("Missing connection_string in headers")
    if not collection:
        raise ValueError("Missing collection in params")

    client = MongoClient(connection_string, serverSelectionTimeoutMS=10000)
    db = client[database]
    return db[collection], client


def _ensure_ttl_index(coll, ttl_field="expires_at"):
    """Ensure a TTL index exists on the collection (idempotent)."""
    index_name = f"ttl_{ttl_field}"
    existing = coll.index_information()
    if index_name not in existing:
        coll.create_index(ttl_field, name=index_name, expireAfterSeconds=0)


def _add_ttl(doc, ttl_hours):
    """Add expires_at field to a document if ttl_hours is set."""
    if ttl_hours and ttl_hours > 0:
        doc["expires_at"] = datetime.datetime.utcnow() + datetime.timedelta(hours=ttl_hours)
    return doc


def _serialize_doc(doc):
    """Convert MongoDB document to JSON-safe dict."""
    if doc is None:
        return None
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    if "expires_at" in doc and isinstance(doc["expires_at"], datetime.datetime):
        doc["expires_at"] = doc["expires_at"].isoformat()
    if "updated_at" in doc and isinstance(doc["updated_at"], datetime.datetime):
        doc["updated_at"] = doc["updated_at"].isoformat()
    if "created_at" in doc and isinstance(doc["created_at"], datetime.datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


# ════════════════════════════════════════════════════════════════════════════════
# WRITE OPERATIONS
# ════════════════════════════════════════════════════════════════════════════════


def write_document(request_data):
    """
    Upsert a single document into a collection.

    Params:
        collection: str - Target collection name
        document: dict - The document to write
        filter: dict - Filter for upsert match (default: uses document._id)
        ttl_hours: int - Hours until auto-expiry (0 = no expiry)
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        coll, client = _get_collection(headers, params)

        document = params.get("document", {})
        filter_query = params.get("filter", {})
        ttl_hours = int(params.get("ttl_hours", 0))

        if not document:
            return {"status": False, "data": {"error": "Missing document in params"}}

        # Add metadata
        now = datetime.datetime.utcnow()
        document["updated_at"] = now
        document.setdefault("created_at", now)

        # Add TTL if specified
        if ttl_hours > 0:
            _add_ttl(document, ttl_hours)
            _ensure_ttl_index(coll)

        # Build filter: use provided filter, or match on _id
        if not filter_query:
            if "_id" in document:
                filter_query = {"_id": document["_id"]}
            else:
                return {"status": False, "data": {"error": "Must provide filter or document._id for upsert"}}

        result = coll.update_one(filter_query, {"$set": document}, upsert=True)

        client.close()

        return {
            "status": True,
            "data": {
                "matched": result.matched_count,
                "modified": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            },
            "message": "Document written successfully",
        }

    except Exception as e:
        return {"status": False, "data": {"error": str(e)}}


def write_many(request_data):
    """
    Upsert multiple documents in bulk.

    Params:
        collection: str - Target collection name
        documents: list[dict] - Documents to write (each must have _id)
        ttl_hours: int - Hours until auto-expiry (0 = no expiry)
        key_field: str - Field to use as upsert key (default: "_id")
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        from pymongo import UpdateOne

        coll, client = _get_collection(headers, params)

        documents = params.get("documents", [])
        ttl_hours = int(params.get("ttl_hours", 0))
        key_field = params.get("key_field", "_id")

        if not documents:
            return {"status": False, "data": {"error": "Missing documents in params"}}

        now = datetime.datetime.utcnow()

        if ttl_hours > 0:
            _ensure_ttl_index(coll)

        operations = []
        for doc in documents:
            doc["updated_at"] = now
            doc.setdefault("created_at", now)

            if ttl_hours > 0:
                _add_ttl(doc, ttl_hours)

            key_value = doc.get(key_field)
            if key_value is None:
                continue

            operations.append(
                UpdateOne({key_field: key_value}, {"$set": doc}, upsert=True)
            )

        if not operations:
            return {"status": False, "data": {"error": "No valid documents to write (missing key_field)"}}

        result = coll.bulk_write(operations)

        client.close()

        return {
            "status": True,
            "data": {
                "matched": result.matched_count,
                "modified": result.modified_count,
                "upserted": result.upserted_count,
            },
            "message": f"Bulk write completed: {len(operations)} operations",
        }

    except Exception as e:
        return {"status": False, "data": {"error": str(e)}}


# ════════════════════════════════════════════════════════════════════════════════
# READ OPERATIONS
# ════════════════════════════════════════════════════════════════════════════════


def read_document(request_data):
    """
    Read a single document by _id.

    Params:
        collection: str - Target collection name
        document_id: str - The _id to look up
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        coll, client = _get_collection(headers, params)

        document_id = params.get("document_id", "")
        if not document_id:
            return {"status": False, "data": {"error": "Missing document_id"}}

        doc = coll.find_one({"_id": document_id})

        client.close()

        if doc is None:
            return {"status": True, "data": {"document": None}, "message": "Document not found"}

        return {
            "status": True,
            "data": {"document": _serialize_doc(doc)},
            "message": "Document found",
        }

    except Exception as e:
        return {"status": False, "data": {"error": str(e)}}


def lookup(request_data):
    """
    Query documents with flexible filters.

    Params:
        collection: str - Target collection name
        filter: dict - MongoDB query filter
        projection: dict - Fields to include/exclude (optional)
        sort: list - Sort specification, e.g. [["field", -1]] (optional)
        limit: int - Max documents to return (default: 100)
        skip: int - Number of documents to skip (default: 0)
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        coll, client = _get_collection(headers, params)

        filter_query = params.get("filter", {})
        projection = params.get("projection")
        sort_spec = params.get("sort")
        limit = int(params.get("limit", 100))
        skip = int(params.get("skip", 0))

        cursor = coll.find(filter_query, projection)

        if sort_spec:
            cursor = cursor.sort(sort_spec)

        cursor = cursor.skip(skip).limit(limit)

        documents = [_serialize_doc(doc) for doc in cursor]

        client.close()

        return {
            "status": True,
            "data": {"documents": documents, "count": len(documents)},
            "message": f"Found {len(documents)} document(s)",
        }

    except Exception as e:
        return {"status": False, "data": {"error": str(e)}}


# ════════════════════════════════════════════════════════════════════════════════
# SEARCH CACHE (drop-in replacement for google-genai invoke_search output)
# ════════════════════════════════════════════════════════════════════════════════


def search_cache(request_data):
    """
    Query the search cache and return results in the same format as
    google-genai invoke_search: { answer, search_results }.

    This allows tenant workflows to swap their search connector from
    google-genai to mongodb-atlas without changing downstream prompts.

    Params:
        collection: str - Cache collection name (default: "search_cache")
        search_query: str - Original search query to look up
        category: str - Category filter (e.g. "competitor_news", "fixture_preview")
        entity_id: str - Entity identifier (e.g. competitor slug, fixture ID)
        max_age_hours: int - Only return results newer than N hours (default: 24)
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        params.setdefault("collection", "search_cache")
        coll, client = _get_collection(headers, params)

        search_query = params.get("search_query", "")
        category = params.get("category", "")
        entity_id = params.get("entity_id", "")
        max_age_hours = int(params.get("max_age_hours", 24))

        # Build filter
        filter_query = {}

        if entity_id:
            filter_query["entity_id"] = entity_id
        if category:
            filter_query["category"] = category
        if search_query:
            filter_query["search_query"] = search_query

        # Only return fresh results
        if max_age_hours > 0:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=max_age_hours)
            filter_query["updated_at"] = {"$gte": cutoff}

        doc = coll.find_one(filter_query, sort=[("updated_at", -1)])

        client.close()

        if doc is None:
            return {
                "status": True,
                "data": {
                    "answer": "",
                    "search_results": [],
                    "cache_hit": False,
                },
                "message": "No cached result found",
            }

        return {
            "status": True,
            "data": {
                "answer": doc.get("answer", ""),
                "search_results": doc.get("search_results", []),
                "cache_hit": True,
                "cached_at": doc.get("updated_at").isoformat() if isinstance(doc.get("updated_at"), datetime.datetime) else str(doc.get("updated_at", "")),
                "source_provider": doc.get("source_provider", ""),
            },
            "message": "Cache hit",
        }

    except Exception as e:
        return {"status": False, "data": {"answer": "", "search_results": [], "error": str(e)}}


# ════════════════════════════════════════════════════════════════════════════════
# DELETE OPERATIONS
# ════════════════════════════════════════════════════════════════════════════════


def delete_document(request_data):
    """
    Delete a single document by _id.

    Params:
        collection: str - Target collection name
        document_id: str - The _id to delete
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        coll, client = _get_collection(headers, params)

        document_id = params.get("document_id", "")
        if not document_id:
            return {"status": False, "data": {"error": "Missing document_id"}}

        result = coll.delete_one({"_id": document_id})

        client.close()

        return {
            "status": True,
            "data": {"deleted": result.deleted_count},
            "message": f"Deleted {result.deleted_count} document(s)",
        }

    except Exception as e:
        return {"status": False, "data": {"error": str(e)}}


def delete_many(request_data):
    """
    Delete documents matching a filter.

    Params:
        collection: str - Target collection name
        filter: dict - MongoDB query filter for documents to delete
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        coll, client = _get_collection(headers, params)

        filter_query = params.get("filter", {})
        if not filter_query:
            return {"status": False, "data": {"error": "Must provide filter for delete_many (safety check)"}}

        result = coll.delete_many(filter_query)

        client.close()

        return {
            "status": True,
            "data": {"deleted": result.deleted_count},
            "message": f"Deleted {result.deleted_count} document(s)",
        }

    except Exception as e:
        return {"status": False, "data": {"error": str(e)}}
