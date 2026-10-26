"""Role-scoped AI operations; provider credentials are never returned."""
from ..api import route
from ..db import reader
from ..ai import pipeline
from ..schemas import AIStatusOut, RoutingOut
from .common import load_application


@route('GET','/api/v1/ai/status',summary='AI provider mode, budget and fallback state',tag='ai',roles=('ADMIN',),response=AIStatusOut)
def ai_status(ctx):
    return pipeline.status()


@route('GET','/api/v1/applications/{application_id}/routing',summary='Deterministic advisory routing with evidence links',tag='ai',response=RoutingOut)
def application_routing(ctx):
    with reader() as c:
        app=load_application(c,ctx.user,ctx.path['application_id'])
        return pipeline.routing(c,app['id'])
