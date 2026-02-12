from core.database.neo4j.driver import Neo4jClient


def consolidate_schemas(request_data):
    """
    Combine multiple extracted schema results into a single consolidated schema.
    Neo4j MERGE operations will handle deduplication.
    
    Args:
        request_data (dict): Contains params with array of extracted schema results
        
    Returns:
        dict: Combined entities and relationships
    """
    params = request_data.get("params", {})
    schemas = params.get("schemas", [])
    
    consolidated = {
        "entities": [],
        "relationships": []
    }
    
    for schema in schemas:
        extracted_data = schema.get("value", {}).get("data", {})
    
        entities = extracted_data.get("extracted_entities", [])
        consolidated["entities"].extend(entities)
        
        relationships = extracted_data.get("extracted_relationships", [])
        consolidated["relationships"].extend(relationships)
    
    return {
        "status": True,
        "message": "Schemas consolidated successfully",
        "data": consolidated
    }


def create_knowledge_graph(request_data):
    """
    Create a knowledge graph in Neo4j based on extracted entities and relationships.
    
    Args:
        request_data (dict): Contains headers for DB connection and params with extracted data
    """
    headers = request_data.get("headers")
    
    db = Neo4jClient(
        uri=headers.get("uri"),
        username=headers.get("username"),
        password=headers.get("password"),
    )

    params = request_data.get("params")
    nodetriples = params.get("nodetriples", {})
    entities = nodetriples.get("entities", [])
    relationships = nodetriples.get("relationships", [])

    result = {
        "entities": [],
        "relationships": []
    }

    for entity in entities:
        abstract_type = entity.get("abstract_type")
        concrete_value = entity.get("concrete_value")
        fields = entity.get("fields", [])
        
        properties = {
            "name": concrete_value
        }
        for field in fields:
            properties[field["name"]] = field["value"]
        
        records, summary, keys = db._driver.execute_query(
            """
            CALL apoc.merge.node($labels, $primary_key, $properties)
            YIELD node
            RETURN id(node) as node_id, node
            """,
            labels=[abstract_type],
            primary_key={"name": concrete_value},
            properties=properties,
            database_="neo4j",
        )

        for record in records:
            result["entities"].append({
                "id": record["node_id"],
                "node": dict(record["node"]),
            })

    for rel in relationships:
        abstract_relation = rel.get("abstract_relation", "")
        head_entity = rel.get("head_entity", "")
        tail_entity = rel.get("tail_entity", "")
        properties = rel.get("properties", {})

        head_id = next((entity["id"] for entity in result["entities"] 
                       if entity["node"]["name"] == head_entity), None)
        tail_id = next((entity["id"] for entity in result["entities"] 
                       if entity["node"]["name"] == tail_entity), None)

        if head_id is not None and tail_id is not None:
            records, summary, keys = db._driver.execute_query(
                """
                MATCH (head) WHERE id(head) = $head_id
                MATCH (tail) WHERE id(tail) = $tail_id
                CALL apoc.create.relationship(head, $relation, $properties, tail)
                YIELD rel
                RETURN rel
                """,
                head_id=head_id,
                tail_id=tail_id,
                relation=abstract_relation,
                properties=properties,
                database_="neo4j",
            )
            
            for record in records:
                result["relationships"].append({
                    "relationship": record["rel"],
                    "type": record["rel"].type,
                    "properties": dict(record["rel"].items())
                })

    return {
        "status": True, 
        "message": "Knowledge graph created successfully",
        "data": result
    }


def query_graph(request_data):
    """
    Query the Neo4j knowledge graph for a specific entity, optionally filtered by relationship type.
    
    Args:
        request_data (dict): Contains:
            - headers: DB connection info
            - params: Query parameters including:
                - entity: Entity label to search for
                - limit (optional): Maximum number of results to return
                
    Returns:
        dict: Query results containing matched entities and relationships
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})
    
    db = Neo4jClient(
        uri=headers.get("uri"),
        username=headers.get("username"),
        password=headers.get("password"),
    )

    entity = params.get("entity")
    limit = params.get("limit", 100)

    result = {
        "entities": [],
        "relationships": []
    }

    if not entity:
        return {
            "status": False,
            "message": "Entity parameter is required",
            "data": result
        }
    
    print("> entity", entity)

    records, summary, keys = db._driver.execute_query(
        """
        CALL apoc.cypher.run("MATCH (n:" + $entity + ") 
        RETURN DISTINCT n as source_node", {}) YIELD value
        RETURN value.source_node as source_node
        LIMIT $limit
        """,
        entity=entity,
        limit=limit,
        database_="neo4j",
    )

    for record in records:
        source = record["source_node"]
        source_data = {
            "id": source.element_id,
            "labels": list(source.labels),
            "properties": dict(source)
        }
        if source_data not in result["entities"]:
            result["entities"].append(source_data)

    return {
        "status": True,
        "message": "Query executed successfully",
        "data": result
    }