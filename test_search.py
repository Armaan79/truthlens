from news_search import search_news

claim = (
    "Jio Platforms IPO became the first global public issue "
    "to receive over 1 crore applications"
)

results = search_news(claim, max_results=10)

for item in results:
    print(item.get("source"), "|", item.get("title"))