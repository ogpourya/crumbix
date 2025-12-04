import sys
import os
import time
import threading
import queue
from datetime import datetime
from urllib.parse import urlparse

# Third-party imports
import click
import browser_cookie3
import tldextract
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.theme import Theme

# Setup Rich Console for pretty output
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "magenta",
    "brand": "bold blue"
})
console = Console(theme=custom_theme)

def get_netscape_format(cookie):
    """
    Converts a cookie object to a Netscape formatted string.
    """
    domain = cookie.domain
    flag = "TRUE" if domain.startswith(".") else "FALSE"
    path = cookie.path
    secure = "TRUE" if cookie.secure else "FALSE"
    expires = int(cookie.expires) if cookie.expires else 0
    expiration = str(expires) if expires != 0 else "0"
    name = cookie.name
    value = cookie.value

    return f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}"

def extract_domain(url):
    """
    Extracts the main domain from a URL.
    Handles standard domains (google.com) and local/IPs (localhost, 127.0.0.1).
    """
    # Ensure scheme exists for parser
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    
    # Force offline mode by providing an empty tuple for suffix_list_urls
    # This tells tldextract to NEVER try to download updates and use the internal snapshot
    no_fetch_extract = tldextract.TLDExtract(suffix_list_urls=())
    extracted = no_fetch_extract(url)
    
    # 1. Standard Domain (e.g., google.com)
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"
        
    # 2. Localhost / Intranet / IP (e.g., localhost, 127.0.0.1)
    parsed = urlparse(url)
    if parsed.hostname:
        return parsed.hostname
        
    return None

def fetch_cookies_threaded(loader, target_domain, result_queue):
    """Runs the blocking loader in a separate thread."""
    try:
        # We try to fetch ONLY for the domain to speed it up.
        # Note: browser_cookie3 might return a cookie jar or list.
        cj = loader(domain_name=target_domain)
        result_queue.put(("success", list(cj)))
    except Exception as e:
        result_queue.put(("error", e))

@click.command()
@click.argument("url")
@click.option(
    "--browser", "-b",
    type=click.Choice(["chrome", "firefox", "brave", "edge", "chromium", "opera", "safari"], case_sensitive=False),
    default="chrome",
    help="The browser to extract cookies from."
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    help="Custom output filename."
)
def main(url, browser, output):
    """
    Crumbix: The Modern Cookie Extractor.
    
    Extracts cookies from your browser and saves them in Netscape format
    (compatible with wget, curl, youtube-dl, etc.).
    """
    
    # 1. Branding Header
    console.print(Panel.fit(
        f"[brand]🍪 CRUMBIX[/brand]\n"
        f"[dim]Target: [highlight]{url}[/highlight][/dim]",
        border_style="blue",
        padding=(1, 2)
    ))

    # 2. Parse Domain
    try:
        target_domain = extract_domain(url)
    except Exception as e:
        # Fallback if tldextract fails completely (rare in offline mode but possible)
        parsed = urlparse(url)
        target_domain = parsed.hostname

    if not target_domain:
        console.print(f"[error]❌ Invalid URL:[/error] Could not determine a domain from '{url}'")
        sys.exit(1)

    if not output:
        output = f"{target_domain}.cookies.txt"

    # 3. Resolve Browser Loader
    loader_map = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "brave": browser_cookie3.brave,
        "edge": browser_cookie3.edge,
        "chromium": browser_cookie3.chromium,
        "opera": browser_cookie3.opera,
        "safari": browser_cookie3.safari,
    }
    loader = loader_map.get(browser.lower())

    # 4. Threaded Extraction
    result_queue = queue.Queue()
    extraction_thread = threading.Thread(
        target=fetch_cookies_threaded,
        args=(loader, target_domain, result_queue),
        daemon=True
    )

    cookies = []
    
    with Progress(
        SpinnerColumn(style="bold magenta"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=None), # Spacer
        console=console,
        transient=True # Disappear when done
    ) as progress:
        
        task = progress.add_task(f"Searching {browser.capitalize()} storage for [cyan]{target_domain}[/cyan]...", total=None)
        
        extraction_thread.start()
        
        # Keep the main thread alive to animate the spinner
        # while waiting for the background thread
        while extraction_thread.is_alive():
            time.sleep(0.1)
            
        # Check results
        if not result_queue.empty():
            status, data = result_queue.get()
            if status == "success":
                cookies = data
            else:
                # Handle Errors
                error_msg = str(data)
                console.print(f"\n[error]❌ Failed to extract cookies from {browser}[/error]")
                
                if "Permission denied" in error_msg or "locked" in error_msg.lower():
                    console.print(Panel(
                        "[yellow]The browser database is locked or protected.[/yellow]\n\n"
                        "1. [bold]Close the browser[/bold] completely and try again.\n"
                        "2. On macOS/Linux, you might need sudo/keyring permissions.",
                        title="Troubleshooting",
                        border_style="yellow"
                    ))
                else:
                    console.print(f"[dim]Error details: {error_msg}[/dim]")
                sys.exit(1)

    # 5. Save & Summary
    if not cookies:
        console.print(Panel(
            f"[warning]⚠️  No cookies found for {target_domain}[/warning]\n\n"
            f"- Are you logged in on {browser}?\n"
            f"- Did you visit {target_domain} recently?",
            border_style="yellow"
        ))
        sys.exit(0)

    try:
        with open(output, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write(f"# Generated by Crumbix on {datetime.now()}\n")
            f.write("# http://curl.haxx.se/rfc/cookie_spec.html\n\n")
            
            for cookie in cookies:
                f.write(get_netscape_format(cookie) + "\n")
                
        console.print(f"[success]✅ Extracted {len(cookies)} cookies![/success]")
        console.print(f"📁 [dim]Saved to:[/dim] [link=file://{os.path.abspath(output)}]{output}[/link]")
        
    except IOError as e:
        console.print(f"[error]❌ File Error:[/error] {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
