 "url_citation": {
          "url": "https://www.example.com/web-search-result",
          "title": "Title of the web search result",
          "content": "Content of the web search result", // Added by OpenRouter if available
          "start_index": 100, // The index of the first character of the URL citation in the message.
          "end_index": 200 // The index of the last character of the URL citation in the message.
        }
      }
 
q: str # 查询关键词 required
format: str = "json"
lang: str = "zh-CN"
safesearch: str = "2" # StrictMode 2
engines: str = "google" # 'google,bing'


# test url