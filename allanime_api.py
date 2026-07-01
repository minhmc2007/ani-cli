#!/usr/bin/env python3
"""AllAnime API helper — bypasses Cloudflare via Playwright browser context.

Usage:
  python3 allanime_api.py --search "one piece"
  python3 allanime_api.py --episodes "2P7kFgthrEfRRkcdm" --mode sub
  python3 allanime_api.py --stream "2P7kFgthrEfRRkcdm" --mode sub --episode 2
  python3 allanime_api.py --stream "2P7kFgthrEfRRkcdm" --mode sub --episode 2 --quality 1080
"""
import asyncio, json, sys, os, base64, subprocess, hashlib, tempfile, argparse, platform
from playwright.async_api import async_playwright

KEY_HEX = hashlib.sha256(b'Xot36i3lK3:v1').hexdigest()

def _is_termux():
    return (os.environ.get('PLAYWRIGHT_BROWSERS_PATH') == '0' or
            platform.system() == 'Linux' and
            ('com.termux' in os.environ.get('PATH', '') or
             os.path.exists('/data/data/com.termux')))

def _get_chromium_path():
    return os.environ.get('CHROMIUM_PATH', '/data/data/com.termux/files/usr/bin/chromium-browser')

DECODE_MAP = {
    '01':'9','08':'0','09':'1','0a':'2','0b':'3','0c':'4','0d':'5','0e':'6','0f':'7','00':'8',
    '50':'h','51':'i','52':'j','53':'k','54':'l','55':'m','56':'n','57':'o','58':'p','59':'a','5a':'b','5b':'c','5c':'d','5d':'e','5e':'f','5f':'g',
    '60':'X','61':'Y','62':'Z','63':'[','64':'\\\\','65':']','66':'^','67':'_','68':'P','69':'Q','6a':'R','6b':'S','6c':'T','6d':'U','6e':'V','6f':'W',
    '70':'H','71':'I','72':'J','73':'K','74':'L','75':'M','76':'N','77':'O','78':'@','79':'A','7a':'B','7b':'C','7c':'D','7d':'E','7e':'F','7f':'G',
    '40':'x','41':'y','42':'z','48':'p','49':'q','4a':'r','4b':'s','4c':'t','4d':'u','4e':'v','4f':'w',
    '15':'-','16':'.','02':':','17':'/','07':'?','05':'=','12':'*','13':'+','14':',','03':';',
    '1b':'#','46':'~','19':'!','1c':'$','1e':'&','10':'(','11':')','1d':'%'
}

def decrypt_tobeparsed(blob_b64):
    if not blob_b64: return ''
    raw = base64.b64decode(blob_b64)
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(raw); tmp.close()
    try:
        with open(tmp.name, 'rb') as f:
            f.seek(1); iv = f.read(12).hex()
        fsize = os.path.getsize(tmp.name)
        ct_len = fsize - 13 - 16
        with open(tmp.name, 'rb') as f:
            f.seek(13); ct = f.read(ct_len)
        proc = subprocess.run(
            ['openssl', 'enc', '-d', '-aes-256-ctr', '-K', KEY_HEX, '-iv', iv+'00000002', '-nosalt', '-nopad'],
            input=ct, capture_output=True, timeout=10
        )
        return proc.stdout.decode('utf-8', errors='replace')
    finally:
        os.unlink(tmp.name)

def decode_xx_url(encoded):
    if not encoded or not encoded.startswith('--'): return encoded
    pairs = [encoded[i:i+2] for i in range(2, len(encoded), 2)]
    return ''.join(DECODE_MAP.get(p, '') for p in pairs)

class AllAnimeClient:
    """Single-page browser client that keeps Cloudflare clearance alive."""
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self._pw = None
        self._browser = None
        self._page = None

    async def __aenter__(self):
        self._pw = await async_playwright().__aenter__()
        launch_opts = {'headless': True}
        if _is_termux():
            os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
            cp = _get_chromium_path()
            if os.path.exists(cp):
                launch_opts['executablePath'] = cp
                launch_opts.setdefault('args', []).extend(['--no-sandbox', '--disable-setuid-sandbox'])
                if self.verbose:
                    print(f"[INFO] Using Termux Chromium: {cp}", file=sys.stderr)
            elif self.verbose:
                print(f"[WARN] Chromium not found at {cp}. Set CHROMIUM_PATH env var or install: pkg install x11-repo chromium", file=sys.stderr)
        self._browser = await self._pw.chromium.launch(**launch_opts)
        ctx = await self._browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        )
        self._page = await ctx.new_page()
        try:
            await self._page.goto("https://isekai2nd.com/anime", wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(3)
        if self.verbose:
            print(f"[OK] Page loaded: {self._page.url}", file=sys.stderr)
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()

    async def api_get(self, params_dict):
        return await self._page.evaluate("""async (params) => {
            const qs = Object.entries(params)
                .map(([k, v]) => k + '=' + encodeURIComponent(v))
                .join('&');
            const resp = await fetch('https://api.allanime.day/api?' + qs, {
                headers: {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://youtu-chan.com', 'Origin': 'https://youtu-chan.com'}
            });
            return {status: resp.status, body: await resp.text()};
        }""", params_dict)

    async def api_post(self, payload):
        return await self._page.evaluate("""async (payload) => {
            const resp = await fetch('https://api.allanime.day/api', {
                method: 'POST',
                headers: {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://youtu-chan.com', 'Origin': 'https://youtu-chan.com', 'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            return {status: resp.status, body: await resp.text()};
        }""", payload)

    async def search(self, query, mode='sub'):
        gql = 'query($search: SearchInput $limit: Int $page: Int $translationType: VaildTranslationTypeEnumType $countryOrigin: VaildCountryOriginEnumType) { shows(search: $search limit: $limit page: $page translationType: $translationType countryOrigin: $countryOrigin) { edges { _id name availableEpisodes __typename } } }'
        payload = {
            'variables': {
                'search': {'allowAdult': False, 'allowUnknown': False, 'query': query},
                'limit': 40, 'page': 1,
                'translationType': mode,
                'countryOrigin': 'ALL'
            },
            'query': gql
        }
        result = await self.api_post(payload)
        data = json.loads(result['body'])
        if self.verbose:
            print(f"[DEBUG] Search response status: {result['status']}", file=sys.stderr)
        shows = data.get('data', {}).get('shows', {}).get('edges', [])
        return [(s['_id'], s['name'], s.get('availableEpisodes', {}).get(mode, 0)) for s in shows]

    async def get_episodes(self, show_id, mode='sub'):
        gql = 'query ($showId: String!) { show(_id: $showId) { _id availableEpisodesDetail } }'
        payload = {'variables': {'showId': show_id}, 'query': gql}
        result = await self.api_post(payload)
        data = json.loads(result['body'])
        if self.verbose:
            print(f"[DEBUG] Episodes response status: {result['status']}", file=sys.stderr)
        detail = data.get('data', {}).get('show', {}).get('availableEpisodesDetail', {})
        eps = detail.get(mode, [])
        return sorted(eps, key=float)

    async def _fetch_page(self, url, referer=None):
        """Fetch a page URL using the browser context (bypasses Cloudflare)."""
        if self.verbose:
            print(f"[DEBUG] Fetching: {url[:200]}", file=sys.stderr)
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': referer or 'https://youtu-chan.com'}
        return await self._page.evaluate("""async ({url, headers}) => {
            try {
                const resp = await fetch(url, {headers: headers, credentials: 'include'});
                return {status: resp.status, body: await resp.text()};
            } catch(e) {
                return {status: 0, body: 'fetch_error: ' + e.message};
            }
        }""", {'url': url, 'headers': headers})

    async def _fetch_via_page_goto(self, url):
        """Navigate to a page and return its content."""
        if self.verbose:
            print(f"[DEBUG] Fetch via goto: {url[:200]}", file=sys.stderr)
        try:
            resp = await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            content = await self._page.content()
            status = resp.status if resp else 0
            return {'status': status, 'body': content}
        except Exception as e:
            if self.verbose:
                print(f"[WARN] goto failed: {e}", file=sys.stderr)
            return {'status': 0, 'body': ''}

    async def _resolve_clock_url(self, url, quality_label):
        """Resolve a /apivtwo/clock?id=... URL by fetching clock.json, return list of (resolution, url) tuples."""
        base = 'https://allanime.day'
        clock_url = base + url.replace('/clock?', '/clock.json?', 1)
        if self.verbose:
            print(f"[DEBUG] Resolving clock URL: {clock_url}", file=sys.stderr)
        result = await self._fetch_page(clock_url)
        if result['status'] != 200:
            if self.verbose:
                print(f"[WARN] Clock fetch failed: {result['status']}", file=sys.stderr)
            return []
        try:
            data = json.loads(result['body'])
        except json.JSONDecodeError:
            if self.verbose:
                print(f"[WARN] Invalid clock JSON", file=sys.stderr)
            return []
        links = data.get('links', [])
        streams = []
        for link in links:
            url_str = link.get('url', '')
            res = link.get('resolutionStr', '')
            if url_str:
                # Make relative URLs absolute
                if url_str.startswith('/'):
                    url_str = base + url_str
                streams.append((res, url_str))
        return streams

    async def _resolve_mp4upload(self, url):
        """Scrape mp4upload page for direct mp4 link."""
        if self.verbose:
            print(f"[DEBUG] Scraping mp4upload: {url}", file=sys.stderr)
        result = await self._fetch_page(url, referer='https://www.mp4upload.com')
        import re
        match = re.search(r'src:\s*"([^"]+)"', result['body'])
        if match:
            return match.group(1)
        return None

    async def _resolve_via_ytdlp(self, url):
        """Use yt-dlp to extract the direct video URL from an embed/page."""
        import subprocess as sp
        try:
            proc = await asyncio.create_subprocess_exec(
                'yt-dlp', '-g', '--no-warnings', url,
                stdout=sp.PIPE, stderr=sp.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode == 0:
                lines = stdout.decode().strip().split('\n')
                if lines:
                    return lines[0]
            if self.verbose:
                print(f"[WARN] yt-dlp failed (code {proc.returncode}): {stderr.decode()[:200]}", file=sys.stderr)
        except FileNotFoundError:
            if self.verbose:
                print(f"[WARN] yt-dlp not found", file=sys.stderr)
        except asyncio.TimeoutError:
            if self.verbose:
                print(f"[WARN] yt-dlp timed out", file=sys.stderr)
        return None

    async def get_stream_url(self, show_id, mode='sub', episode='1', quality='best'):
        params_dict = {
            'variables': json.dumps({'showId': show_id, 'translationType': mode, 'episodeString': episode}),
            'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': 'd405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec'}})
        }
        result = await self.api_get(params_dict)
        body = result['body']
        
        if self.verbose:
            print(f"[DEBUG] Stream API status: {result['status']}", file=sys.stderr)
        
        data = json.loads(body)
        
        if 'tobeparsed' not in body:
            if 'errors' in data:
                raise Exception(f"API error: {data['errors']}")
            raise Exception(f"Unexpected response: {body[:200]}")
        
        decrypted = decrypt_tobeparsed(data['data']['tobeparsed'])
        if self.verbose:
            print(f"[DEBUG] Decrypted successfully", file=sys.stderr)
        
        ep = json.loads(decrypted).get('episode', {})
        sources = ep.get('sourceUrls', [])
        
        if self.verbose:
            print(f"[DEBUG] Found {len(sources)} sources:", file=sys.stderr)
            for s in sources:
                raw = s.get('sourceUrl', '')
                decoded = decode_xx_url(raw)
                print(f"  {s.get('sourceName', '?')} (p={s.get('priority', '?')})", file=sys.stderr)
                print(f"    raw: {raw[:200]}", file=sys.stderr)
                print(f"    dec: {decoded[:200]}", file=sys.stderr)
        
        candidates = []
        for s in sources:
            url = decode_xx_url(s.get('sourceUrl', ''))
            candidates.append((s.get('priority', 99), s.get('sourceName', ''), url))
        candidates.sort(key=lambda x: x[0])
        
        if self.verbose:
            print(f"[DEBUG] Sorted candidates by priority:", file=sys.stderr)
            for p, n, u in candidates:
                print(f"  p={p} {n}: {u[:120]}", file=sys.stderr)
        
        # Group candidates by type
        direct_urls = []      # URLs that can be played directly (fast4speed, etc.)
        scrape_urls = []      # URLs that need scraping (mp4upload)
        embed_urls = []       # Embed URLs that need yt-dlp or browser
        clock_urls = []       # Clock URLs (currently broken)
        
        for prio, name, src_url in candidates:
            if src_url.startswith('/apivtwo/clock'):
                clock_urls.append((prio, name, src_url))
            elif 'mp4upload' in src_url:
                scrape_urls.append((prio, name, src_url))
            elif 'tools.fast4speed' in src_url or 'yt-mp4' in src_url.lower() or any(x in src_url for x in ['.mp4', '.m3u8', '.ts']):
                direct_urls.append((prio, name, src_url))
            else:
                embed_urls.append((prio, name, src_url))
        
        if self.verbose:
            print(f"[DEBUG] Direct: {len(direct_urls)}, Scrape: {len(scrape_urls)}, Embed: {len(embed_urls)}, Clock: {len(clock_urls)}", file=sys.stderr)
        
        # Try in order: direct → scrape → embed → clock (fallback)
        for prio, name, src_url in direct_urls:
            if self.verbose:
                print(f"[DEBUG] Direct URL: {name} (p={prio})", file=sys.stderr)
            return src_url
        
        for prio, name, src_url in scrape_urls:
            if self.verbose:
                print(f"[DEBUG] Scraping: {name} (p={prio})", file=sys.stderr)
            resolved = await self._resolve_mp4upload(src_url)
            if resolved:
                if self.verbose:
                    print(f"[DEBUG] Scraped URL: {resolved[:200]}", file=sys.stderr)
                return resolved
            if self.verbose:
                print(f"[DEBUG] mp4upload scraping failed", file=sys.stderr)
        
        for prio, name, src_url in embed_urls:
            if self.verbose:
                print(f"[DEBUG] Embed URL: {name} (p={prio}), trying yt-dlp", file=sys.stderr)
            resolved = await self._resolve_via_ytdlp(src_url)
            if resolved:
                if self.verbose:
                    print(f"[DEBUG] yt-dlp resolved: {resolved[:200]}", file=sys.stderr)
                return resolved
            if self.verbose:
                print(f"[DEBUG] yt-dlp failed for {name}", file=sys.stderr)
        
        # Fallback: return the raw decoded URL of the best candidate
        if candidates:
            if self.verbose:
                print(f"[WARN] No source resolved, returning raw URL", file=sys.stderr)
            return candidates[0][2]
        return None


async def main():
    parser = argparse.ArgumentParser(description='AllAnime API helper')
    parser.add_argument('--search', help='Search anime')
    parser.add_argument('--episodes', help='Get episodes list for show ID')
    parser.add_argument('--stream', help='Get stream URL for show ID')
    parser.add_argument('--graphql', help='Raw GraphQL query string (use with --variables)')
    parser.add_argument('--variables', help='JSON variables string (use with --graphql)')
    parser.add_argument('--mode', default='sub', choices=['sub', 'dub'])
    parser.add_argument('--episode', default='1')
    parser.add_argument('--quality', default='best')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    async with AllAnimeClient(verbose=args.verbose) as client:
        if args.graphql:
            vars_dict = json.loads(args.variables) if args.variables else {}
            payload = {'query': args.graphql, 'variables': vars_dict}
            result = await client.api_post(payload)
            if args.verbose:
                print(f"[STATUS] {result['status']}", file=sys.stderr)
            print(result['body'])

        elif args.search:
            results = await client.search(args.search, args.mode)
            for sid, name, eps in results:
                print(f"{sid}\t{name} ({eps} episodes)")

        elif args.episodes:
            eps = await client.get_episodes(args.episodes, args.mode)
            for ep in eps:
                print(ep)

        elif args.stream:
            url = await client.get_stream_url(args.stream, args.mode, args.episode, args.quality)
            if url:
                print(url)
            else:
                print("ERROR: No stream URL found", file=sys.stderr)
                sys.exit(1)

        else:
            parser.print_help()

if __name__ == '__main__':
    asyncio.run(main())
