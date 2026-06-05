import sys
import asyncio
from pathlib import Path
from curator.mcp_server import build_server

server = build_server()

async def main():
    file_path = "/Users/shin/Library/Mobile Documents/com~apple~CloudDocs/Zotero/[Project] COLMAP_free_Reconstruction/Multiple_View_Geometry_in_Computer_Vision-EN.pdf"
    res = await server.call_tool("curator_get_pdf_toc", {"file_path": file_path})
    print(res)

asyncio.run(main())
