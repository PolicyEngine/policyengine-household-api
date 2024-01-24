from werkzeug.wrappers import Request

class AnalyticsWrapper:
  def __init__(self, app):
    self.app = app

  def __call__(self, environ, start_response):
    request = Request(environ)
    print("Middleware working on:")
    print(request)
    return self.app(environ, start_response)