from urllib.parse import urlparse

url = "https://graph.microsoft.com/v1.0/me?$skip=5"
parsed = urlparse(url)
print(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")

url2 = "https://graph.microsoft.com/v1.0/me?%24skip=5"
parsed2 = urlparse(url2)
print(f"{parsed2.scheme}://{parsed2.netloc}{parsed2.path}")
