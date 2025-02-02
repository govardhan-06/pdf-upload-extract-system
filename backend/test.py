from celery import Celery

# Initialize Celery app (replace 'your_project' with your actual app name)
app = Celery('pdf_processor', broker='redis://:695011@localhost:6379/0')

app.conf.update(
    accept_content=['json', 'pickle'],  # Allow pickle
    task_serializer='json',
    result_serializer='json',
)

# Inspect registered tasks
inspector = app.control.inspect()
registered_tasks = inspector.registered()

# Print registered tasks
if registered_tasks:
    for worker, tasks in registered_tasks.items():
        print(f"Worker: {worker}")
        for task in tasks:
            print(f"  - {task}")
else:
    print("No tasks registered or no workers are running.")
