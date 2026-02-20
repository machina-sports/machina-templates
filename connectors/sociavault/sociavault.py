def get_credits(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE_URL = "https://api.sociavault.com/v1"

    def _request(endpoint, params=None, api_key=None):
        url = f"{BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in clean.items())
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode())
            if isinstance(raw, dict) and "success" in raw and "credits_used" in raw:
                if not raw.get("success"):
                    return {"error": True, "message": raw.get("message", "API returned success=false")}
                return raw.get("data", raw)
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    try:
        headers = request_data.get("headers", {})
        api_key = headers.get("api_key", "")
        if not api_key:
            return {"status": False, "data": None, "message": "API key is required. Set the SociaVault-API-Key secret."}

        response = _request("/credits", api_key=api_key)
        if isinstance(response, dict) and response.get("error"):
            status_code = response.get("status_code", "unknown")
            if status_code == 401:
                return {"status": False, "data": None, "message": "Invalid API key. Please check your SociaVault-API-Key secret."}
            return {"status": False, "data": None, "message": f"API error ({status_code}): {response.get('message', '')}"}

        return {
            "status": True,
            "data": {
                "credits": response.get("credits", 0),
                "subscription_status": response.get("subscription_status", "unknown")
            },
            "message": f"Credits: {response.get('credits', 0)}"
        }
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching credits: {str(e)}"}


def instagram_get_profile(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE_URL = "https://api.sociavault.com/v1"

    def _request(endpoint, params=None, api_key=None):
        url = f"{BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in clean.items())
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode())
            if isinstance(raw, dict) and "success" in raw and "credits_used" in raw:
                if not raw.get("success"):
                    return {"error": True, "message": raw.get("message", "API returned success=false")}
                return raw.get("data", raw)
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _check_error(response):
        if isinstance(response, dict) and response.get("error"):
            status_code = response.get("status_code", "unknown")
            if status_code == 401:
                return {"status": False, "data": None, "message": "Invalid API key. Please check your SociaVault-API-Key secret."}
            if status_code == 402:
                return {"status": False, "data": None, "message": "Insufficient credits. Please top up your SociaVault account."}
            return {"status": False, "data": None, "message": f"API error ({status_code}): {response.get('message', '')}"}
        return None

    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        api_key = headers.get("api_key", "")
        if not api_key:
            return {"status": False, "data": None, "message": "API key is required. Set the SociaVault-API-Key secret."}

        handle = params.get("handle", "")
        if not handle:
            return {"status": False, "data": None, "message": "Parameter 'handle' is required (Instagram username)."}

        trim = params.get("trim", "true")
        response = _request("/scrape/instagram/profile", params={"handle": handle, "trim": trim}, api_key=api_key)

        err = _check_error(response)
        if err:
            return err

        user = response.get("data", {}).get("user", {}) if isinstance(response.get("data"), dict) else {}
        if not user:
            user = response.get("user", {})
        if not user:
            return {"status": False, "data": None, "message": f"No profile data returned for handle '{handle}'."}

        profile = {
            "user_id": str(user.get("id", "")),
            "username": str(user.get("username", "")),
            "full_name": str(user.get("full_name", "")),
            "biography": str(user.get("biography", "") or ""),
            "followers_count": int(user.get("edge_followed_by", {}).get("count", 0)) if isinstance(user.get("edge_followed_by"), dict) else 0,
            "following_count": int(user.get("edge_follow", {}).get("count", 0)) if isinstance(user.get("edge_follow"), dict) else 0,
            "media_count": int(user.get("edge_owner_to_timeline_media", {}).get("count", 0)) if isinstance(user.get("edge_owner_to_timeline_media"), dict) else 0,
            "is_verified": bool(user.get("is_verified", False)),
            "is_private": bool(user.get("is_private", False)),
            "profile_pic_url": str(user.get("profile_pic_url_hd", user.get("profile_pic_url", "")) or ""),
            "external_url": str(user.get("external_url", "") or ""),
            "category": str(user.get("category_name", "") or ""),
        }

        recent_videos = []
        try:
            video_edges = user.get("edge_felix_video_timeline", {})
            if isinstance(video_edges, dict):
                edges = video_edges.get("edges", [])
                if isinstance(edges, list):
                    for edge in edges[:10]:
                        if not isinstance(edge, dict):
                            continue
                        node = edge.get("node", {})
                        if not isinstance(node, dict):
                            continue
                        caption_text = ""
                        cap_edges = node.get("edge_media_to_caption", {})
                        if isinstance(cap_edges, dict):
                            cap_list = cap_edges.get("edges", [])
                            if isinstance(cap_list, list) and len(cap_list) > 0:
                                cap_node = cap_list[0]
                                if isinstance(cap_node, dict):
                                    caption_text = str(cap_node.get("node", {}).get("text", "") or "")
                        like_data = node.get("edge_liked_by", node.get("edge_media_preview_like", {}))
                        like_count = int(like_data.get("count", 0)) if isinstance(like_data, dict) else 0
                        recent_videos.append({
                            "id": str(node.get("id", "")),
                            "shortcode": str(node.get("shortcode", "")),
                            "caption": caption_text,
                            "view_count": int(node.get("video_view_count", 0) or 0),
                            "like_count": like_count,
                            "comment_count": int(node.get("edge_media_to_comment", {}).get("count", 0)) if isinstance(node.get("edge_media_to_comment"), dict) else 0,
                            "taken_at": node.get("taken_at_timestamp", ""),
                            "thumbnail_url": str(node.get("thumbnail_src", "") or ""),
                        })
        except Exception:
            recent_videos = []

        return {
            "status": True,
            "data": {
                "profile": profile,
                "recent_videos": recent_videos,
                "platform": "instagram"
            },
            "message": f"Profile retrieved for @{profile.get('username', handle)}: {profile.get('followers_count', 0)} followers"
        }
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching Instagram profile: {str(e)}"}


def instagram_get_posts(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE_URL = "https://api.sociavault.com/v1"

    def _request(endpoint, params=None, api_key=None):
        url = f"{BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in clean.items())
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode())
            if isinstance(raw, dict) and "success" in raw and "credits_used" in raw:
                if not raw.get("success"):
                    return {"error": True, "message": raw.get("message", "API returned success=false")}
                return raw.get("data", raw)
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _check_error(response):
        if isinstance(response, dict) and response.get("error"):
            status_code = response.get("status_code", "unknown")
            if status_code == 401:
                return {"status": False, "data": None, "message": "Invalid API key. Please check your SociaVault-API-Key secret."}
            if status_code == 402:
                return {"status": False, "data": None, "message": "Insufficient credits. Please top up your SociaVault account."}
            return {"status": False, "data": None, "message": f"API error ({status_code}): {response.get('message', '')}"}
        return None

    def _normalize_post(item):
        caption_text = ""
        caption = item.get("caption", {})
        if isinstance(caption, dict):
            caption_text = caption.get("text", "")
        elif isinstance(caption, str):
            caption_text = caption
        return {
            "id": item.get("id", ""),
            "shortcode": item.get("code", item.get("shortcode", "")),
            "media_type": item.get("media_type", 0),
            "taken_at": item.get("taken_at", ""),
            "caption": caption_text,
            "play_count": item.get("play_count", 0),
            "comment_count": item.get("comment_count", 0),
            "like_count": item.get("like_count", 0),
            "image_url": item.get("image_versions2", {}).get("candidates", [{}])[0].get("url", "") if isinstance(item.get("image_versions2"), dict) else item.get("thumbnail_url", ""),
            "video_url": item.get("video_url", ""),
        }

    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        api_key = headers.get("api_key", "")
        if not api_key:
            return {"status": False, "data": None, "message": "API key is required. Set the SociaVault-API-Key secret."}

        handle = params.get("handle", "")
        if not handle:
            return {"status": False, "data": None, "message": "Parameter 'handle' is required (Instagram username)."}

        query = {"handle": handle}
        if params.get("next_max_id"):
            query["next_max_id"] = params["next_max_id"]
        if params.get("trim"):
            query["trim"] = params["trim"]

        response = _request("/scrape/instagram/posts", params=query, api_key=api_key)

        err = _check_error(response)
        if err:
            return err

        data = response if isinstance(response, dict) else {}
        # Unwrap inner envelope if present (scrape endpoints return {success, data: {actual_data}})
        if isinstance(data.get("data"), (dict, list)):
            data = data.get("data", data)
        items = data.get("items", data.get("posts", []))
        if not isinstance(items, list):
            items = []

        posts = [_normalize_post(item) for item in items]
        next_max_id = data.get("next_max_id", None)

        # Include debug keys in message for troubleshooting
        resp_keys = list(response.keys()) if isinstance(response, dict) else []
        data_keys = list(data.keys()) if isinstance(data, dict) else []

        return {
            "status": True,
            "data": {
                "posts": posts,
                "count": len(posts),
                "next_max_id": next_max_id,
                "has_more": next_max_id is not None,
                "_debug_resp_keys": resp_keys,
                "_debug_data_keys": data_keys,
                "_debug_items_len": len(items),
                "_debug_response_type": str(type(response).__name__),
                "_debug_success": response.get("success", "MISSING") if isinstance(response, dict) else "NOT_DICT"
            },
            "message": f"Retrieved {len(posts)} posts for @{handle} | resp_keys={resp_keys} | data_keys={data_keys}"
        }
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching Instagram posts: {str(e)}"}


def instagram_get_reels(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE_URL = "https://api.sociavault.com/v1"

    def _request(endpoint, params=None, api_key=None):
        url = f"{BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in clean.items())
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode())
            if isinstance(raw, dict) and "success" in raw and "credits_used" in raw:
                if not raw.get("success"):
                    return {"error": True, "message": raw.get("message", "API returned success=false")}
                return raw.get("data", raw)
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _check_error(response):
        if isinstance(response, dict) and response.get("error"):
            status_code = response.get("status_code", "unknown")
            if status_code == 401:
                return {"status": False, "data": None, "message": "Invalid API key. Please check your SociaVault-API-Key secret."}
            if status_code == 402:
                return {"status": False, "data": None, "message": "Insufficient credits. Please top up your SociaVault account."}
            return {"status": False, "data": None, "message": f"API error ({status_code}): {response.get('message', '')}"}
        return None

    def _normalize_reel(item):
        caption_text = ""
        caption = item.get("caption", {})
        if isinstance(caption, dict):
            caption_text = caption.get("text", "")
        elif isinstance(caption, str):
            caption_text = caption
        return {
            "id": item.get("id", ""),
            "shortcode": item.get("code", item.get("shortcode", "")),
            "media_type": item.get("media_type", 0),
            "taken_at": item.get("taken_at", ""),
            "caption": caption_text,
            "play_count": item.get("play_count", 0),
            "comment_count": item.get("comment_count", 0),
            "like_count": item.get("like_count", 0),
            "image_url": item.get("image_versions2", {}).get("candidates", [{}])[0].get("url", "") if isinstance(item.get("image_versions2"), dict) else item.get("thumbnail_url", ""),
            "video_url": item.get("video_url", ""),
        }

    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        api_key = headers.get("api_key", "")
        if not api_key:
            return {"status": False, "data": None, "message": "API key is required. Set the SociaVault-API-Key secret."}

        handle = params.get("handle", "")
        if not handle:
            return {"status": False, "data": None, "message": "Parameter 'handle' is required (Instagram username)."}

        query = {"handle": handle}
        if params.get("user_id"):
            query["user_id"] = params["user_id"]
        if params.get("max_id"):
            query["max_id"] = params["max_id"]

        response = _request("/scrape/instagram/reels", params=query, api_key=api_key)

        err = _check_error(response)
        if err:
            return err

        data = response if isinstance(response, dict) else {}
        # Unwrap inner envelope if present (scrape endpoints return {success, data: {actual_data}})
        if isinstance(data.get("data"), (dict, list)):
            data = data.get("data", data)
        items = data.get("items", data.get("reels", []))
        if not isinstance(items, list):
            items = []

        reels = [_normalize_reel(item) for item in items]
        max_id = data.get("max_id", data.get("paging_info", {}).get("max_id", None))

        return {
            "status": True,
            "data": {
                "reels": reels,
                "count": len(reels),
                "max_id": max_id,
                "has_more": max_id is not None
            },
            "message": f"Retrieved {len(reels)} reels for @{handle}"
        }
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching Instagram reels: {str(e)}"}


def instagram_get_post_info(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE_URL = "https://api.sociavault.com/v1"

    def _request(endpoint, params=None, api_key=None):
        url = f"{BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in clean.items())
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode())
            if isinstance(raw, dict) and "success" in raw and "credits_used" in raw:
                if not raw.get("success"):
                    return {"error": True, "message": raw.get("message", "API returned success=false")}
                return raw.get("data", raw)
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _check_error(response):
        if isinstance(response, dict) and response.get("error"):
            status_code = response.get("status_code", "unknown")
            if status_code == 401:
                return {"status": False, "data": None, "message": "Invalid API key. Please check your SociaVault-API-Key secret."}
            if status_code == 402:
                return {"status": False, "data": None, "message": "Insufficient credits. Please top up your SociaVault account."}
            return {"status": False, "data": None, "message": f"API error ({status_code}): {response.get('message', '')}"}
        return None

    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        api_key = headers.get("api_key", "")
        if not api_key:
            return {"status": False, "data": None, "message": "API key is required. Set the SociaVault-API-Key secret."}

        url = params.get("url", "")
        if not url:
            return {"status": False, "data": None, "message": "Parameter 'url' is required (full Instagram post/reel URL)."}

        response = _request("/scrape/instagram/post-info", params={"url": url}, api_key=api_key)

        err = _check_error(response)
        if err:
            return err

        data = response if isinstance(response, dict) else {}
        media = data.get("xdt_shortcode_media", data)

        caption_text = ""
        caption_edges = media.get("edge_media_to_caption", {}).get("edges", [])
        if caption_edges:
            caption_text = caption_edges[0].get("node", {}).get("text", "")

        owner = media.get("owner", {})

        post_info = {
            "shortcode": media.get("shortcode", ""),
            "caption": caption_text,
            "play_count": media.get("video_play_count", media.get("play_count", 0)),
            "like_count": media.get("edge_media_preview_like", {}).get("count", 0),
            "comment_count": media.get("edge_media_to_parent_comment", {}).get("count", media.get("edge_media_to_comment", {}).get("count", 0)),
            "owner_username": owner.get("username", ""),
            "owner_id": owner.get("id", ""),
            "is_video": media.get("is_video", False),
            "taken_at": media.get("taken_at_timestamp", ""),
            "display_url": media.get("display_url", ""),
            "video_url": media.get("video_url", ""),
        }

        return {
            "status": True,
            "data": post_info,
            "message": f"Post info retrieved for shortcode {post_info.get('shortcode', 'unknown')}"
        }
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching Instagram post info: {str(e)}"}


def instagram_get_comments(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE_URL = "https://api.sociavault.com/v1"

    def _request(endpoint, params=None, api_key=None):
        url = f"{BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in clean.items())
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode())
            if isinstance(raw, dict) and "success" in raw and "credits_used" in raw:
                if not raw.get("success"):
                    return {"error": True, "message": raw.get("message", "API returned success=false")}
                return raw.get("data", raw)
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _check_error(response):
        if isinstance(response, dict) and response.get("error"):
            status_code = response.get("status_code", "unknown")
            if status_code == 401:
                return {"status": False, "data": None, "message": "Invalid API key. Please check your SociaVault-API-Key secret."}
            if status_code == 402:
                return {"status": False, "data": None, "message": "Insufficient credits. Please top up your SociaVault account."}
            return {"status": False, "data": None, "message": f"API error ({status_code}): {response.get('message', '')}"}
        return None

    def _normalize_comment(item):
        user = item.get("user", {})
        return {
            "id": item.get("pk", item.get("id", "")),
            "text": item.get("text", ""),
            "created_at": item.get("created_at", ""),
            "username": user.get("username", item.get("username", "")),
            "user_id": user.get("pk", user.get("id", "")),
            "like_count": item.get("comment_like_count", item.get("like_count", 0)),
        }

    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        api_key = headers.get("api_key", "")
        if not api_key:
            return {"status": False, "data": None, "message": "API key is required. Set the SociaVault-API-Key secret."}

        url = params.get("url", "")
        if not url:
            return {"status": False, "data": None, "message": "Parameter 'url' is required (full Instagram post/reel URL)."}

        query = {"url": url}
        if params.get("cursor"):
            query["cursor"] = params["cursor"]

        response = _request("/scrape/instagram/comments", params=query, api_key=api_key)

        err = _check_error(response)
        if err:
            return err

        data = response if isinstance(response, dict) else {}
        # Unwrap inner envelope if present (scrape endpoints return {success, data: {actual_data}})
        if isinstance(data.get("data"), (dict, list)):
            data = data.get("data", data)
        items = data.get("comments", data.get("items", []))
        if not isinstance(items, list):
            items = []

        comments = [_normalize_comment(item) for item in items]
        cursor = data.get("next_min_id", data.get("cursor", None))

        return {
            "status": True,
            "data": {
                "comments": comments,
                "count": len(comments),
                "cursor": cursor,
                "has_more": cursor is not None
            },
            "message": f"Retrieved {len(comments)} comments"
        }
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching Instagram comments: {str(e)}"}


def instagram_get_highlights(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE_URL = "https://api.sociavault.com/v1"

    def _request(endpoint, params=None, api_key=None):
        url = f"{BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in clean.items())
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode())
            if isinstance(raw, dict) and "success" in raw and "credits_used" in raw:
                if not raw.get("success"):
                    return {"error": True, "message": raw.get("message", "API returned success=false")}
                return raw.get("data", raw)
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _check_error(response):
        if isinstance(response, dict) and response.get("error"):
            status_code = response.get("status_code", "unknown")
            if status_code == 401:
                return {"status": False, "data": None, "message": "Invalid API key. Please check your SociaVault-API-Key secret."}
            if status_code == 402:
                return {"status": False, "data": None, "message": "Insufficient credits. Please top up your SociaVault account."}
            return {"status": False, "data": None, "message": f"API error ({status_code}): {response.get('message', '')}"}
        return None

    def _normalize_highlight(item):
        return {
            "id": item.get("id", item.get("pk", "")),
            "title": item.get("title", ""),
            "cover_url": item.get("cover_media", {}).get("cropped_image_version", {}).get("url", "") if isinstance(item.get("cover_media"), dict) else item.get("cover_url", ""),
            "media_count": item.get("media_count", 0),
        }

    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        api_key = headers.get("api_key", "")
        if not api_key:
            return {"status": False, "data": None, "message": "API key is required. Set the SociaVault-API-Key secret."}

        handle = params.get("handle", "")
        if not handle:
            return {"status": False, "data": None, "message": "Parameter 'handle' is required (Instagram username)."}

        query = {"handle": handle}
        if params.get("user_id"):
            query["user_id"] = params["user_id"]

        response = _request("/scrape/instagram/highlights", params=query, api_key=api_key)

        err = _check_error(response)
        if err:
            return err

        data = response if isinstance(response, dict) else {}
        # Unwrap inner envelope if present (scrape endpoints return {success, data: {actual_data}})
        if isinstance(data.get("data"), (dict, list)):
            data = data.get("data", data)
        items = data.get("highlights", data.get("items", []))
        if not isinstance(items, list):
            items = []

        highlights = [_normalize_highlight(item) for item in items]

        return {
            "status": True,
            "data": {
                "highlights": highlights,
                "count": len(highlights)
            },
            "message": f"Retrieved {len(highlights)} highlights for @{handle}"
        }
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching Instagram highlights: {str(e)}"}


def instagram_get_transcript(request_data):
    import json
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE_URL = "https://api.sociavault.com/v1"

    def _request(endpoint, params=None, api_key=None):
        url = f"{BASE_URL}{endpoint}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in clean.items())
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        if api_key:
            req.add_header("X-API-Key", api_key)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode())
            if isinstance(raw, dict) and "success" in raw and "credits_used" in raw:
                if not raw.get("success"):
                    return {"error": True, "message": raw.get("message", "API returned success=false")}
                return raw.get("data", raw)
            return raw
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            return {"error": True, "status_code": e.code, "message": body}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _check_error(response):
        if isinstance(response, dict) and response.get("error"):
            status_code = response.get("status_code", "unknown")
            if status_code == 401:
                return {"status": False, "data": None, "message": "Invalid API key. Please check your SociaVault-API-Key secret."}
            if status_code == 402:
                return {"status": False, "data": None, "message": "Insufficient credits. Please top up your SociaVault account."}
            return {"status": False, "data": None, "message": f"API error ({status_code}): {response.get('message', '')}"}
        return None

    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        api_key = headers.get("api_key", "")
        if not api_key:
            return {"status": False, "data": None, "message": "API key is required. Set the SociaVault-API-Key secret."}

        url = params.get("url", "")
        if not url:
            return {"status": False, "data": None, "message": "Parameter 'url' is required (full Instagram video/reel URL)."}

        response = _request("/scrape/instagram/transcript", params={"url": url}, api_key=api_key)

        err = _check_error(response)
        if err:
            return err

        data = response if isinstance(response, dict) else {}
        # Unwrap inner envelope if present (scrape endpoints return {success, data: {actual_data}})
        if isinstance(data.get("data"), (dict, list)):
            data = data.get("data", data)
        items = data.get("transcripts", data.get("items", []))
        if not isinstance(items, list):
            if isinstance(data, dict) and data.get("text"):
                items = [data]
            else:
                items = []

        transcripts = []
        for item in items:
            transcripts.append({
                "id": item.get("id", ""),
                "shortcode": item.get("shortcode", item.get("code", "")),
                "text": item.get("text", item.get("transcript", "")),
            })

        return {
            "status": True,
            "data": {
                "transcripts": transcripts,
                "count": len(transcripts)
            },
            "message": f"Retrieved {len(transcripts)} transcript(s)"
        }
    except Exception as e:
        return {"status": False, "data": None, "message": f"Error fetching Instagram transcript: {str(e)}"}
