from fastapi import APIRouter
from backend.logic import generate_example
from backend.database import conn, c

router = APIRouter()

@router.get('/generate-task')
def get_task(level: int = 1):
    expr, ans = generate_example(level)
    return {'expression': expr, 'answer': ans}

@router.post('/save-session')
def save_session(data: dict):
    telegram_id = data.get('telegram_id', 'local')
    level = int(data.get('level', 1))
    correct = int(data.get('correct', 0))
    wrong = int(data.get('wrong', 0))
    total = int(data.get('total', 10))
    time_ms = int(data.get('time_ms', 0))

    c.execute(
        'INSERT INTO sessions (telegram_id, level, correct, wrong, total, time_ms) VALUES (?,?,?,?,?,?)',
        (telegram_id, level, correct, wrong, total, time_ms)
    )
    conn.commit()
    return {'status': 'ok'}
