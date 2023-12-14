# Start the API
gunicorn -b :$PORT policyengine_api_light.api --timeout 300 --workers 5 &
# Start the redis server
redis-server &
# Start the worker
python3.9 policyengine_api_light/worker.py
