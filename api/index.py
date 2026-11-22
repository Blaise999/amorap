"""Vercel Python Function entry point for AMORAP.

The website assets are in public/. Only /api/* and legacy /uploads/*
requests are routed here by vercel.json.
"""
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Handler

class handler(Handler):
    def dispatch(self,method):
        raw=urlsplit(self.path)
        params=parse_qsl(raw.query,keep_blank_values=True)
        route=next((value for key,value in params if key=='amora_path'),None)
        if route is not None:
            route=route.lstrip('/')
            if not (route.startswith('api/') or route.startswith('uploads/')) or any(part in ('.','..') for part in route.split('/')):
                self.path='/invalid-route'
            else:
                other=[(k,v) for k,v in params if k!='amora_path']
                self.path='/'+route+('?' + urlencode(other) if other else '')
        return super().dispatch(method)
