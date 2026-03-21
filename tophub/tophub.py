import requests
import lxml.html
import json
BASE_URL = "https://tophub.today/topics?p={p}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def read_url(p):
    URL = BASE_URL.format(p=p)
    response = requests.get(URL, headers={"User-Agent": USER_AGENT})
    if response.status_code == 200:
        return response.text
    else:
        return None

def parse_html(html):
    result = []
    doc = lxml.html.fromstring(html)
    topic_list = doc.cssselect("ul.topic-list li div.box")
    for topic in topic_list:
        title = topic.cssselect("h3")[0].text
        desc = topic.cssselect("div.des")[0].text
        time = topic.cssselect("div.msg div.time")[0].text
        react_doc_list = topic.cssselect("div.react-doc-item")
        hot = len(react_doc_list)
        result.append({ "title": title, "desc": desc, "time": time, "hot": hot })
    return result

def main():
    p = 1
    result = []
    while p <= 2:
        html = read_url(p)
        if html is None:
            break
        items = parse_html(html)
        if not items:
            break
        result.extend(items)
        p += 1
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
