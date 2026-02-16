def get_sports_markets(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    SPORTS_TAG_ID = 1
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{GAMMA_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _normalize_market(market):
        clob_token_ids = market.get("clobTokenIds", [])
        outcomes = market.get("outcomes", [])
        outcome_prices = market.get("outcomePrices", [])
        parsed_prices = []
        if outcome_prices:
            for p in outcome_prices:
                try:
                    parsed_prices.append(float(p) if isinstance(p, str) else p)
                except (ValueError, TypeError):
                    parsed_prices.append(None)
        normalized_outcomes = []
        for i, outcome in enumerate(outcomes):
            entry = {"name": outcome}
            if i < len(parsed_prices) and parsed_prices[i] is not None:
                entry["price"] = round(parsed_prices[i], 4)
            if i < len(clob_token_ids):
                entry["clob_token_id"] = clob_token_ids[i]
            normalized_outcomes.append(entry)
        return {
            "id": market.get("id", ""),
            "question": market.get("question", ""),
            "description": market.get("description", ""),
            "slug": market.get("slug", ""),
            "status": "active" if market.get("active") and not market.get("closed") else "closed" if market.get("closed") else "inactive",
            "outcomes": normalized_outcomes,
            "volume": _safe_float(market.get("volume")),
            "volume_24h": _safe_float(market.get("volume24hr")),
            "liquidity": _safe_float(market.get("liquidity")),
            "competitive": market.get("competitive", 0),
            "spread": _safe_float(market.get("spread")),
            "start_date": market.get("startDate", ""),
            "end_date": market.get("endDate", ""),
            "created_at": market.get("createdAt", ""),
            "updated_at": market.get("updatedAt", ""),
            "event_id": market.get("events", [{}])[0].get("id", "") if market.get("events") else "",
            "sports_market_type": market.get("sportsMarketType", ""),
            "game_id": market.get("gameId", ""),
            "clob_token_ids": clob_token_ids,
            "tags": [t.get("label", "") if isinstance(t, dict) else t for t in market.get("tags", [])],
        }

    try:
        params = request_data if isinstance(request_data, dict) else {}
        query = {
            "tag_id": params.get("tag_id", SPORTS_TAG_ID),
            "limit": min(int(params.get("limit", 50)), 100),
            "offset": int(params.get("offset", 0)),
            "active": str(params.get("active", True)).lower(),
            "closed": str(params.get("closed", False)).lower(),
            "order": params.get("order", "volume"),
            "ascending": str(params.get("ascending", False)).lower(),
        }
        if params.get("sports_market_types"):
            query["sports_market_types"] = params["sports_market_types"]
        if params.get("game_id"):
            query["game_id"] = params["game_id"]

        response = _request("/markets", params=query)
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}

        markets = response if isinstance(response, list) else response.get("markets", response)
        if not isinstance(markets, list):
            markets = []
        normalized = [_normalize_market(m) for m in markets]
        return {"status": True, "data": {"markets": normalized, "count": len(normalized), "offset": query["offset"]}, "message": f"Retrieved {len(normalized)} sports markets"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching sports markets: {str(e)}"}


def get_sports_events(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    SPORTS_TAG_ID = 1
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{GAMMA_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _normalize_market(market):
        clob_token_ids = market.get("clobTokenIds", [])
        outcomes = market.get("outcomes", [])
        outcome_prices = market.get("outcomePrices", [])
        parsed_prices = []
        if outcome_prices:
            for p in outcome_prices:
                try:
                    parsed_prices.append(float(p) if isinstance(p, str) else p)
                except (ValueError, TypeError):
                    parsed_prices.append(None)
        normalized_outcomes = []
        for i, outcome in enumerate(outcomes):
            entry = {"name": outcome}
            if i < len(parsed_prices) and parsed_prices[i] is not None:
                entry["price"] = round(parsed_prices[i], 4)
            if i < len(clob_token_ids):
                entry["clob_token_id"] = clob_token_ids[i]
            normalized_outcomes.append(entry)
        return {
            "id": market.get("id", ""),
            "question": market.get("question", ""),
            "description": market.get("description", ""),
            "slug": market.get("slug", ""),
            "status": "active" if market.get("active") and not market.get("closed") else "closed" if market.get("closed") else "inactive",
            "outcomes": normalized_outcomes,
            "volume": _safe_float(market.get("volume")),
            "volume_24h": _safe_float(market.get("volume24hr")),
            "liquidity": _safe_float(market.get("liquidity")),
            "competitive": market.get("competitive", 0),
            "spread": _safe_float(market.get("spread")),
            "start_date": market.get("startDate", ""),
            "end_date": market.get("endDate", ""),
            "created_at": market.get("createdAt", ""),
            "updated_at": market.get("updatedAt", ""),
            "event_id": market.get("events", [{}])[0].get("id", "") if market.get("events") else "",
            "sports_market_type": market.get("sportsMarketType", ""),
            "game_id": market.get("gameId", ""),
            "clob_token_ids": clob_token_ids,
            "tags": [t.get("label", "") if isinstance(t, dict) else t for t in market.get("tags", [])],
        }

    def _normalize_event(event):
        markets = event.get("markets", [])
        return {
            "id": event.get("id", ""),
            "title": event.get("title", ""),
            "description": event.get("description", ""),
            "slug": event.get("slug", ""),
            "status": "active" if event.get("active") and not event.get("closed") else "closed" if event.get("closed") else "inactive",
            "start_date": event.get("startDate", ""),
            "end_date": event.get("endDate", ""),
            "created_at": event.get("createdAt", ""),
            "updated_at": event.get("updatedAt", ""),
            "volume": _safe_float(event.get("volume")),
            "liquidity": _safe_float(event.get("liquidity")),
            "competitive": event.get("competitive", 0),
            "market_count": len(markets),
            "markets": [_normalize_market(m) for m in markets] if markets else [],
            "tags": [t.get("label", "") if isinstance(t, dict) else t for t in event.get("tags", [])],
            "series_id": event.get("seriesId", ""),
        }

    try:
        params = request_data if isinstance(request_data, dict) else {}
        query = {
            "tag_id": params.get("tag_id", SPORTS_TAG_ID),
            "limit": min(int(params.get("limit", 50)), 100),
            "offset": int(params.get("offset", 0)),
            "active": str(params.get("active", True)).lower(),
            "closed": str(params.get("closed", False)).lower(),
            "order": params.get("order", "volume"),
            "ascending": str(params.get("ascending", False)).lower(),
        }
        if params.get("series_id"):
            query["series_id"] = params["series_id"]

        response = _request("/events", params=query)
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}

        events = response if isinstance(response, list) else response.get("events", response)
        if not isinstance(events, list):
            events = []
        normalized = [_normalize_event(e) for e in events]
        return {"status": True, "data": {"events": normalized, "count": len(normalized), "offset": query["offset"]}, "message": f"Retrieved {len(normalized)} sports events"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching sports events: {str(e)}"}


def get_series(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{GAMMA_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    try:
        params = request_data if isinstance(request_data, dict) else {}
        query = {
            "limit": min(int(params.get("limit", 100)), 200),
            "offset": int(params.get("offset", 0)),
        }

        response = _request("/series", params=query)
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}

        series_list = response if isinstance(response, list) else response.get("series", response)
        if not isinstance(series_list, list):
            series_list = []
        normalized = []
        for s in series_list:
            normalized.append({
                "id": s.get("id", ""),
                "title": s.get("title", ""),
                "slug": s.get("slug", ""),
                "description": s.get("description", ""),
                "image": s.get("image", ""),
                "created_at": s.get("createdAt", ""),
                "updated_at": s.get("updatedAt", ""),
            })
        return {"status": True, "data": {"series": normalized, "count": len(normalized)}, "message": f"Retrieved {len(normalized)} series"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching series: {str(e)}"}


def get_market_details(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{GAMMA_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _normalize_market(market):
        clob_token_ids = market.get("clobTokenIds", [])
        outcomes = market.get("outcomes", [])
        outcome_prices = market.get("outcomePrices", [])
        parsed_prices = []
        if outcome_prices:
            for p in outcome_prices:
                try:
                    parsed_prices.append(float(p) if isinstance(p, str) else p)
                except (ValueError, TypeError):
                    parsed_prices.append(None)
        normalized_outcomes = []
        for i, outcome in enumerate(outcomes):
            entry = {"name": outcome}
            if i < len(parsed_prices) and parsed_prices[i] is not None:
                entry["price"] = round(parsed_prices[i], 4)
            if i < len(clob_token_ids):
                entry["clob_token_id"] = clob_token_ids[i]
            normalized_outcomes.append(entry)
        return {
            "id": market.get("id", ""),
            "question": market.get("question", ""),
            "description": market.get("description", ""),
            "slug": market.get("slug", ""),
            "status": "active" if market.get("active") and not market.get("closed") else "closed" if market.get("closed") else "inactive",
            "outcomes": normalized_outcomes,
            "volume": _safe_float(market.get("volume")),
            "volume_24h": _safe_float(market.get("volume24hr")),
            "liquidity": _safe_float(market.get("liquidity")),
            "competitive": market.get("competitive", 0),
            "spread": _safe_float(market.get("spread")),
            "start_date": market.get("startDate", ""),
            "end_date": market.get("endDate", ""),
            "created_at": market.get("createdAt", ""),
            "updated_at": market.get("updatedAt", ""),
            "event_id": market.get("events", [{}])[0].get("id", "") if market.get("events") else "",
            "sports_market_type": market.get("sportsMarketType", ""),
            "game_id": market.get("gameId", ""),
            "clob_token_ids": clob_token_ids,
            "tags": [t.get("label", "") if isinstance(t, dict) else t for t in market.get("tags", [])],
        }

    try:
        params = request_data if isinstance(request_data, dict) else {}
        market_id = params.get("market_id", "")
        slug = params.get("slug", "")
        if not market_id and not slug:
            return {"status": False, "data": None, "message": "Either market_id or slug is required"}

        endpoint = f"/markets/{slug}" if slug else f"/markets/{market_id}"
        response = _request(endpoint)
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}
        if not response or (isinstance(response, dict) and not response.get("id")):
            return {"status": False, "data": None, "message": f"Market not found: {market_id or slug}"}

        normalized = _normalize_market(response)
        return {"status": True, "data": normalized, "message": f"Retrieved market: {normalized.get('question', '')}"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching market details: {str(e)}"}


def get_event_details(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{GAMMA_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _normalize_market(market):
        clob_token_ids = market.get("clobTokenIds", [])
        outcomes = market.get("outcomes", [])
        outcome_prices = market.get("outcomePrices", [])
        parsed_prices = []
        if outcome_prices:
            for p in outcome_prices:
                try:
                    parsed_prices.append(float(p) if isinstance(p, str) else p)
                except (ValueError, TypeError):
                    parsed_prices.append(None)
        normalized_outcomes = []
        for i, outcome in enumerate(outcomes):
            entry = {"name": outcome}
            if i < len(parsed_prices) and parsed_prices[i] is not None:
                entry["price"] = round(parsed_prices[i], 4)
            if i < len(clob_token_ids):
                entry["clob_token_id"] = clob_token_ids[i]
            normalized_outcomes.append(entry)
        return {
            "id": market.get("id", ""),
            "question": market.get("question", ""),
            "description": market.get("description", ""),
            "slug": market.get("slug", ""),
            "status": "active" if market.get("active") and not market.get("closed") else "closed" if market.get("closed") else "inactive",
            "outcomes": normalized_outcomes,
            "volume": _safe_float(market.get("volume")),
            "volume_24h": _safe_float(market.get("volume24hr")),
            "liquidity": _safe_float(market.get("liquidity")),
            "competitive": market.get("competitive", 0),
            "spread": _safe_float(market.get("spread")),
            "start_date": market.get("startDate", ""),
            "end_date": market.get("endDate", ""),
            "created_at": market.get("createdAt", ""),
            "updated_at": market.get("updatedAt", ""),
            "event_id": market.get("events", [{}])[0].get("id", "") if market.get("events") else "",
            "sports_market_type": market.get("sportsMarketType", ""),
            "game_id": market.get("gameId", ""),
            "clob_token_ids": clob_token_ids,
            "tags": [t.get("label", "") if isinstance(t, dict) else t for t in market.get("tags", [])],
        }

    def _normalize_event(event):
        markets = event.get("markets", [])
        return {
            "id": event.get("id", ""),
            "title": event.get("title", ""),
            "description": event.get("description", ""),
            "slug": event.get("slug", ""),
            "status": "active" if event.get("active") and not event.get("closed") else "closed" if event.get("closed") else "inactive",
            "start_date": event.get("startDate", ""),
            "end_date": event.get("endDate", ""),
            "created_at": event.get("createdAt", ""),
            "updated_at": event.get("updatedAt", ""),
            "volume": _safe_float(event.get("volume")),
            "liquidity": _safe_float(event.get("liquidity")),
            "competitive": event.get("competitive", 0),
            "market_count": len(markets),
            "markets": [_normalize_market(m) for m in markets] if markets else [],
            "tags": [t.get("label", "") if isinstance(t, dict) else t for t in event.get("tags", [])],
            "series_id": event.get("seriesId", ""),
        }

    try:
        params = request_data if isinstance(request_data, dict) else {}
        event_id = params.get("event_id", "")
        slug = params.get("slug", "")
        if not event_id and not slug:
            return {"status": False, "data": None, "message": "Either event_id or slug is required"}

        endpoint = f"/events/{slug}" if slug else f"/events/{event_id}"
        response = _request(endpoint)
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}
        if not response or (isinstance(response, dict) and not response.get("id")):
            return {"status": False, "data": None, "message": f"Event not found: {event_id or slug}"}

        normalized = _normalize_event(response)
        return {"status": True, "data": normalized, "message": f"Retrieved event: {normalized.get('title', '')}"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching event details: {str(e)}"}


def get_market_prices(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    CLOB_BASE_URL = "https://clob.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{CLOB_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _is_error(response):
        return isinstance(response, dict) and response.get("error")

    try:
        params = request_data if isinstance(request_data, dict) else {}
        token_id = params.get("token_id", "")
        token_ids = params.get("token_ids", [])

        if not token_id and not token_ids:
            return {"status": False, "data": None, "message": "Either token_id or token_ids is required"}

        if token_id and not token_ids:
            midpoint = _request("/midpoint", params={"token_id": token_id})
            if _is_error(midpoint):
                return {"status": False, "data": None, "message": f"API error ({midpoint.get('status_code', 'unknown')}): {midpoint.get('message', '')}"}

            buy_price = _request("/price", params={"token_id": token_id, "side": "BUY"})
            sell_price = _request("/price", params={"token_id": token_id, "side": "SELL"})

            price_data = {
                "token_id": token_id,
                "midpoint": _safe_float(midpoint.get("mid")),
                "buy_price": _safe_float(buy_price.get("price")) if not _is_error(buy_price) else None,
                "sell_price": _safe_float(sell_price.get("price")) if not _is_error(sell_price) else None,
            }
            return {"status": True, "data": price_data, "message": "Price data retrieved"}
        else:
            prices = []
            for tid in token_ids[:20]:
                midpoint = _request("/midpoint", params={"token_id": tid})
                if not _is_error(midpoint):
                    prices.append({"token_id": tid, "midpoint": _safe_float(midpoint.get("mid"))})
            return {"status": True, "data": {"prices": prices, "count": len(prices)}, "message": f"Retrieved prices for {len(prices)} tokens"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching market prices: {str(e)}"}


def get_order_book(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    CLOB_BASE_URL = "https://clob.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{CLOB_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    try:
        params = request_data if isinstance(request_data, dict) else {}
        token_id = params.get("token_id", "")
        if not token_id:
            return {"status": False, "data": None, "message": "token_id is required"}

        response = _request("/book", params={"token_id": token_id})
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}

        bids = response.get("bids", [])
        asks = response.get("asks", [])
        best_bid = _safe_float(bids[0].get("price")) if bids else 0
        best_ask = _safe_float(asks[0].get("price")) if asks else 0
        spread = round(best_ask - best_bid, 4) if best_bid and best_ask else None

        book = {
            "token_id": token_id,
            "bids": [{"price": _safe_float(b.get("price")), "size": _safe_float(b.get("size"))} for b in bids],
            "asks": [{"price": _safe_float(a.get("price")), "size": _safe_float(a.get("size"))} for a in asks],
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "bid_depth": len(bids),
            "ask_depth": len(asks),
        }
        return {"status": True, "data": book, "message": f"Order book retrieved ({len(bids)} bids, {len(asks)} asks)"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching order book: {str(e)}"}


def get_sports_market_types(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{GAMMA_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    try:
        response = _request("/sports/market-types")
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}
        return {"status": True, "data": response, "message": "Sports market types retrieved"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching sports market types: {str(e)}"}


def search_markets(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    SPORTS_TAG_ID = 1
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{GAMMA_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _normalize_market(market):
        clob_token_ids = market.get("clobTokenIds", [])
        outcomes = market.get("outcomes", [])
        outcome_prices = market.get("outcomePrices", [])
        parsed_prices = []
        if outcome_prices:
            for p in outcome_prices:
                try:
                    parsed_prices.append(float(p) if isinstance(p, str) else p)
                except (ValueError, TypeError):
                    parsed_prices.append(None)
        normalized_outcomes = []
        for i, outcome in enumerate(outcomes):
            entry = {"name": outcome}
            if i < len(parsed_prices) and parsed_prices[i] is not None:
                entry["price"] = round(parsed_prices[i], 4)
            if i < len(clob_token_ids):
                entry["clob_token_id"] = clob_token_ids[i]
            normalized_outcomes.append(entry)
        return {
            "id": market.get("id", ""),
            "question": market.get("question", ""),
            "description": market.get("description", ""),
            "slug": market.get("slug", ""),
            "status": "active" if market.get("active") and not market.get("closed") else "closed" if market.get("closed") else "inactive",
            "outcomes": normalized_outcomes,
            "volume": _safe_float(market.get("volume")),
            "volume_24h": _safe_float(market.get("volume24hr")),
            "liquidity": _safe_float(market.get("liquidity")),
            "competitive": market.get("competitive", 0),
            "spread": _safe_float(market.get("spread")),
            "start_date": market.get("startDate", ""),
            "end_date": market.get("endDate", ""),
            "created_at": market.get("createdAt", ""),
            "updated_at": market.get("updatedAt", ""),
            "event_id": market.get("events", [{}])[0].get("id", "") if market.get("events") else "",
            "sports_market_type": market.get("sportsMarketType", ""),
            "game_id": market.get("gameId", ""),
            "clob_token_ids": clob_token_ids,
            "tags": [t.get("label", "") if isinstance(t, dict) else t for t in market.get("tags", [])],
        }

    try:
        params = request_data if isinstance(request_data, dict) else {}
        query = params.get("query", "").lower()
        limit = min(int(params.get("limit", 20)), 50)

        event_params = {
            "tag_id": params.get("tag_id", SPORTS_TAG_ID),
            "limit": min(limit * 2, 100),
            "active": "true",
            "closed": "false",
            "order": "volume",
            "ascending": "false",
        }

        response = _request("/events", params=event_params)
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}

        events = response if isinstance(response, list) else response.get("events", response)
        if not isinstance(events, list):
            events = []

        if query:
            events = [
                e for e in events
                if query in e.get("title", "").lower()
                or query in e.get("description", "").lower()
                or query in e.get("slug", "").lower()
            ]

        all_markets = []
        for e in events[:limit]:
            markets = e.get("markets", [])
            smt = params.get("sports_market_types", "")
            if smt:
                markets = [m for m in markets if m.get("sportsMarketType", "") == smt]
            all_markets.extend([_normalize_market(m) for m in markets])

        result = all_markets[:limit]
        return {"status": True, "data": {"markets": result, "count": len(result), "query": query or "(all sports)"}, "message": f"Found {len(result)} markets"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error searching markets: {str(e)}"}


def get_price_history(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    CLOB_BASE_URL = "https://clob.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{CLOB_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    try:
        params = request_data if isinstance(request_data, dict) else {}
        token_id = params.get("token_id", "")
        if not token_id:
            return {"status": False, "data": None, "message": "token_id is required"}

        query = {
            "market": token_id,
            "interval": params.get("interval", "max"),
            "fidelity": int(params.get("fidelity", 120)),
        }

        response = _request("/prices-history", params=query)
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}

        history = response.get("history", []) if isinstance(response, dict) else response
        if not isinstance(history, list):
            history = []
        return {"status": True, "data": {"history": history, "count": len(history), "token_id": token_id}, "message": f"Retrieved {len(history)} price data points"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching price history: {str(e)}"}


def get_last_trade_price(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    CLOB_BASE_URL = "https://clob.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    def _request(endpoint, params=None):
        url = f"{CLOB_BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    try:
        params = request_data if isinstance(request_data, dict) else {}
        token_id = params.get("token_id", "")
        if not token_id:
            return {"status": False, "data": None, "message": "token_id is required"}

        response = _request("/last-trade-price", params={"token_id": token_id})
        if isinstance(response, dict) and response.get("error"):
            return {"status": False, "data": None, "message": f"API error ({response.get('status_code', 'unknown')}): {response.get('message', '')}"}

        return {"status": True, "data": {"token_id": token_id, "price": _safe_float(response.get("price")), "side": response.get("side", "")}, "message": f"Last trade price: {response.get('price', 'N/A')}"}
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching last trade price: {str(e)}"}
