def invoke_update_article_image(request_data):

    params = request_data.get("params", {})

    articles_data = params.get("articles-data", [])
    uploaded_images = params.get("uploaded-images", [])

    # Create lookup dictionary for images by article_id
    images_dict = {
        img.get("article_id"): img.get("image_path") for img in uploaded_images
    }

    # Merge image_path into articles based on article_id
    articles_parsed = [
        {**article, "image_path": images_dict.get(article.get("article_id"))}
        for article in articles_data
    ]

    return {
        "status": True,
        "message": "Images merged into articles successfully.",
        "data": {"articles-parsed": articles_parsed},
    }
