from flask import Flask, jsonify, request, abort, send_from_directory, render_template, session
from tariff_utils import calculate_start_time, get_best_tariff_windows
import os
import json
from datetime import datetime, timedelta
import random
from collections import defaultdict
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor

api_key = os.getenv("OCTOPUS_KEY")

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')

# Vocabulary quiz settings are kept here because both the HTML page and
# regenerate endpoint need the same source file and allowed count values.
VOCAB_QUESTION_PATH = os.path.join(
    app.root_path,
    'static',
    'English',
    'Vocabulary',
    'questions.json',
)
VOCAB_DEFAULT_COUNT = 10
VOCAB_ALLOWED_COUNTS = [1, 5, 10, 15, 20, 25, 30]
VOCAB_ALLOWED_TYPES = [
    'word_meaning',
    'reverse_meaning',
    'fill_in_blank',
    'alternative_word',
    'part_of_speech',
]
VOCAB_RECENT_QUESTION_SESSION_KEY = 'recent_vocab_question_ids'
VOCAB_RECENT_QUESTION_LIMIT = 40
VOCAB_PROFILE_SESSION_KEY = 'active_vocab_profile_key'


@app.route('/')
def hello_world():
    return jsonify(message="Hello, Happy Flasking!")

@app.route('/api/spec')
def api_spec():
    return send_from_directory('static', 'api_spec.yaml')


@app.route('/xml/<path:filename>')
def serve_xml(filename: str):
    """Serve XML files from the /static/xml directory via /xml/<filename>.xml.

    If the requested file does not exist, return a JSON 404 with a clear message.
    Only .xml files are allowed (anything else 404s).
    """
    if not filename.lower().endswith('.xml'):
        abort(404)

    # Resolve from the intended static subdirectory and reject missing files.
    xml_dir = os.path.join(app.root_path, 'static', 'xml')
    file_path = os.path.join(xml_dir, filename)

    if not os.path.isfile(file_path):
        return jsonify(error="File not found"), 404

    return send_from_directory(xml_dir, filename, mimetype='application/xml')


@app.route('/html/<path:filename>')
def serve_html(filename: str):
    """Serve HTML files from the /static/html directory via /html/<filename>.html.

    If the requested file does not exist, return a JSON 404 with a clear message.
    Only .html files are allowed (anything else 404s).
    """
    if not filename.lower().endswith('.html'):
        abort(404)

    # Mirror the XML route, but restrict this endpoint to static HTML files.
    html_dir = os.path.join(app.root_path, 'static', 'html')
    file_path = os.path.join(html_dir, filename)

    if not os.path.isfile(file_path):
        return jsonify(error="File not found"), 404

    return send_from_directory(html_dir, filename, mimetype='text/html')


@app.route('/tariff')
def tariff():
    num_hours_str = request.args.get('numHours', default=None)
    
    if num_hours_str is None:
        return jsonify(error="numHours parameter is required"), 400
    
    try:
        num_hours = float(num_hours_str)
    except ValueError:
        return jsonify(error="numHours must be a number"), 400

    try:
        start_time_str = calculate_start_time(num_hours, api_key)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except RuntimeError as error:
        return jsonify(error=str(error)), 502

    return jsonify(startTime=start_time_str)


@app.route('/octopus')
def octopus():
    # The Octopus page presents fixed appliance durations as a compact table.
    durations = [1, 1.5, 2, 2.5, 3, 3.5]
    page_error = None
    window_rows = []

    try:
        window_rows = get_best_tariff_windows(durations, api_key)
    except RuntimeError as error:
        page_error = str(error)

    for row in window_rows:
        # Convert tariff utility output into labels that the template can print.
        if row.get('error'):
            row['duration_label'] = f"{row['duration_hours']:g} hours"
            continue

        row['duration_label'] = f"{row['duration_hours']:g} hours"
        row['start_label'] = row['start_time'].strftime('%d %b %Y, %H:%M')
        row['end_label'] = row['end_time'].strftime('%d %b %Y, %H:%M')
        row['total_tariff_label'] = f"{row['total_tariff']:.2f} p/kWh"
        row['average_tariff_label'] = f"{row['average_tariff']:.2f} p/kWh"
        row['is_credit'] = row['total_tariff'] < 0
        row['slot_details'] = [
            {
                'start_label': slot['start_time'].strftime('%d %b %Y, %H:%M'),
                'end_label': slot['end_time'].strftime('%d %b %Y, %H:%M'),
                'tariff_label': f"{slot['tariff']:.2f} p/kWh",
            }
            for slot in row.get('slots', [])
        ]

    return render_template(
        'octopus.html',
        rows=window_rows,
        page_error=page_error,
    )


def _get_database_url():
    """Resolve database URL from known environment variable names."""
    return (
        os.getenv('DATABASE_URL')
        or os.getenv('DADATBASE_URL')
        or os.getenv('DB_URL')
    )


def _get_db_connection():
    database_url = _get_database_url()
    if not database_url:
        raise RuntimeError(
            'Database URL is not configured. Set DATABASE_URL (or DADATBASE_URL/DB_URL).'
        )
    return psycopg2.connect(database_url)


def _fetch_vocab_profiles():
    with _get_db_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT profile_key, display_name, is_guest, is_default
                FROM vocab_profiles
                ORDER BY is_default DESC, id ASC
                """
            )
            profiles = cursor.fetchall()

    if not profiles:
        raise RuntimeError('No vocabulary profiles are configured.')

    return [dict(row) for row in profiles]


def _resolve_active_profile(profiles):
    requested_user = request.args.get('user', type=str)
    if requested_user:
        requested_user = requested_user.strip().lower()

    requested_profile = request.args.get('profile', type=str)
    if requested_profile:
        requested_profile = requested_profile.strip().lower()

    available = {profile['profile_key']: profile for profile in profiles}
    by_display_name = {
        str(profile.get('display_name', '')).strip().lower(): profile
        for profile in profiles
        if profile.get('display_name')
    }

    session_profile_key = session.get(VOCAB_PROFILE_SESSION_KEY)

    if requested_profile and requested_profile in available:
        active_profile_key = requested_profile
    elif requested_user and requested_user in available:
        active_profile_key = requested_user
    elif requested_user and requested_user in by_display_name:
        active_profile_key = by_display_name[requested_user]['profile_key']
    elif session_profile_key in available:
        active_profile_key = session_profile_key
    else:
        default_profile = next((profile for profile in profiles if profile.get('is_default')), profiles[0])
        active_profile_key = default_profile['profile_key']

    session[VOCAB_PROFILE_SESSION_KEY] = active_profile_key
    return available[active_profile_key], [profile['profile_key'] for profile in profiles]


def _load_word_weights(profile):
    if profile.get('is_guest'):
        return {}

    with _get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT target_word, weight
                FROM vocab_word_state
                WHERE profile_id = (SELECT id FROM vocab_profiles WHERE profile_key = %s)
                """,
                (profile['profile_key'],),
            )
            rows = cursor.fetchall()

    return {target_word: float(weight) for target_word, weight in rows}


def _weighted_sample_without_replacement(questions, weights, sample_size):
    if sample_size <= 0:
        return []

    keyed_questions = []
    for question in questions:
        target_word = question.get('target_word', '')
        weight = max(0.01, weights.get(target_word, 1.0))
        u = random.random() or 1e-9
        key = u ** (1.0 / weight)
        keyed_questions.append((key, question))

    keyed_questions.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in keyed_questions[:sample_size]]


def _apply_weight_transition(weight, consecutive_correct, was_correct):
    if not was_correct:
        if weight in (0.5, 1.0):
            return 2.0, 0
        if weight == 2.0:
            return 4.0, 0
        return 4.0, 0

    next_cc = consecutive_correct + 1
    if weight == 4.0 and next_cc >= 2:
        return 2.0, 0
    if weight == 2.0 and next_cc >= 2:
        return 1.0, 0
    if weight == 1.0 and next_cc >= 3:
        return 0.5, 0
    return weight, next_cc


def _record_vocab_submission(profile_key, word_outcomes, quiz_id=None):
    with _get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, is_guest FROM vocab_profiles WHERE profile_key = %s', (profile_key,))
            profile_row = cursor.fetchone()
            if not profile_row:
                raise ValueError('Unknown profile.')

            profile_id, is_guest = profile_row
            if is_guest:
                return {'updated_words': 0, 'skipped_updates': True}

            updated_words = 0
            for target_word, was_correct in word_outcomes.items():
                cursor.execute(
                    """
                    SELECT weight, consecutive_correct
                    FROM vocab_word_state
                    WHERE profile_id = %s AND target_word = %s
                    FOR UPDATE
                    """,
                    (profile_id, target_word),
                )
                state_row = cursor.fetchone()
                current_weight = float(state_row[0]) if state_row else 1.0
                current_cc = state_row[1] if state_row else 0

                new_weight, new_cc = _apply_weight_transition(current_weight, current_cc, was_correct)

                cursor.execute(
                    """
                    INSERT INTO vocab_word_state (profile_id, target_word, weight, consecutive_correct, last_answered_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (profile_id, target_word)
                    DO UPDATE SET
                        weight = EXCLUDED.weight,
                        consecutive_correct = EXCLUDED.consecutive_correct,
                        last_answered_at = EXCLUDED.last_answered_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (profile_id, target_word, Decimal(str(new_weight)), new_cc),
                )

                cursor.execute(
                    """
                    INSERT INTO vocab_answer_events (profile_id, target_word, was_correct, submitted_at, quiz_id, created_at)
                    VALUES (%s, %s, %s, NOW(), %s, NOW())
                    """,
                    (profile_id, target_word, was_correct, quiz_id),
                )
                updated_words += 1

    return {'updated_words': updated_words, 'skipped_updates': False}


def _get_vocab_count(default=VOCAB_DEFAULT_COUNT):
    """Return a supported quiz size, falling back to the default for bad input."""
    count = request.args.get('count', default=default, type=int)
    if count not in VOCAB_ALLOWED_COUNTS:
        count = default
    return count


def _get_vocab_types():
    """Return supported question types parsed from a comma-separated query list."""
    raw_types = request.args.get('types', default='', type=str)

    if not raw_types:
        return list(VOCAB_ALLOWED_TYPES)

    requested_types = [question_type.strip() for question_type in raw_types.split(',') if question_type.strip()]
    filtered_types = [question_type for question_type in requested_types if question_type in VOCAB_ALLOWED_TYPES]

    if not filtered_types:
        return list(VOCAB_ALLOWED_TYPES)

    return filtered_types


def _load_vocab_questions():
    """Load the vocabulary question bank and ensure it keeps the expected shape."""
    with open(VOCAB_QUESTION_PATH, encoding='utf-8') as question_file:
        questions = json.load(question_file)

    if not isinstance(questions, list):
        raise ValueError('Vocabulary question bank must be a JSON array.')

    return questions


def _sample_vocab_questions(count, selected_types=None, profile=None):
    """Pick random questions, preferring IDs the current user has not just seen."""
    questions = _load_vocab_questions()

    if selected_types:
        questions = [question for question in questions if question.get('type') in selected_types]

    sample_size = min(count, len(questions))
    recent_question_ids = session.get(VOCAB_RECENT_QUESTION_SESSION_KEY, [])
    recent_question_id_set = set(recent_question_ids)
    fresh_questions = [
        question for question in questions
        if question.get('id') not in recent_question_id_set
    ]

    if not sample_size:
        selected_questions = []
    else:
        working_pool = fresh_questions if len(fresh_questions) >= sample_size else questions
        if profile and not profile.get('is_guest'):
            weights = _load_word_weights(profile)
            selected_questions = _weighted_sample_without_replacement(working_pool, weights, sample_size)
        else:
            selected_questions = random.sample(working_pool, sample_size)

    selected_ids = [question.get('id') for question in selected_questions if question.get('id')]
    session[VOCAB_RECENT_QUESTION_SESSION_KEY] = (
        recent_question_ids + selected_ids
    )[-VOCAB_RECENT_QUESTION_LIMIT:]

    sampled_questions = []
    for question in selected_questions:
        question_copy = dict(question)
        choices = [dict(choice) for choice in question_copy.get('choices', [])]
        random.shuffle(choices)
        question_copy['choices'] = choices
        sampled_questions.append(question_copy)

    return sampled_questions


@app.route('/vocab')
def vocab():
    """Render the vocabulary quiz page with an initial random question set."""
    count = _get_vocab_count()

    selected_types = _get_vocab_types()

    try:
        profiles = _fetch_vocab_profiles()
        active_profile, available_profile_keys = _resolve_active_profile(profiles)
        questions = _sample_vocab_questions(count, selected_types, active_profile)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        return render_template(
            'vocab.html',
            questions=[],
            selected_count=count,
            allowed_counts=VOCAB_ALLOWED_COUNTS,
            default_count=VOCAB_DEFAULT_COUNT,
            allowed_types=VOCAB_ALLOWED_TYPES,
            page_error=str(error),
            profiles=[],
            active_profile_key='',
            default_profile_key='',
        ), 500

    default_profile_key = next(
        (profile['profile_key'] for profile in profiles if profile.get('is_default')),
        profiles[0]['profile_key'],
    )

    return render_template(
        'vocab.html',
        questions=questions,
        selected_count=count,
        allowed_counts=VOCAB_ALLOWED_COUNTS,
        default_count=VOCAB_DEFAULT_COUNT,
        allowed_types=VOCAB_ALLOWED_TYPES,
        page_error=None,
        profiles=profiles,
        active_profile_key=active_profile['profile_key'],
        default_profile_key=default_profile_key,
    )


@app.route('/vocab/questions')
def vocab_questions():
    """Return a fresh question set for no-refresh quiz regeneration."""
    count = _get_vocab_count()

    selected_types = _get_vocab_types()

    try:
        profiles = _fetch_vocab_profiles()
        active_profile, available_profile_keys = _resolve_active_profile(profiles)
        questions = _sample_vocab_questions(count, selected_types, active_profile)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        return jsonify(error=str(error)), 500

    return jsonify(questions=questions, count=len(questions), selected_types=selected_types, active_profile=active_profile['profile_key'])


@app.route('/vocab/feedback', methods=['POST'])
def vocab_feedback():
    """Accept first-attempt outcomes and update adaptive word state."""
    data = request.get_json(silent=True) or {}
    profile_key = str(data.get('profile_key', '')).strip().lower()
    results = data.get('results', [])
    quiz_id = data.get('quiz_id')

    if not profile_key:
        return jsonify(error='profile_key is required'), 400

    if not isinstance(results, list):
        return jsonify(error='results must be a list'), 400

    word_buckets = defaultdict(list)
    for row in results:
        if not isinstance(row, dict):
            continue
        target_word = str(row.get('target_word', '')).strip()
        if not target_word:
            continue
        was_correct = bool(row.get('first_attempt_correct'))
        word_buckets[target_word].append(was_correct)

    word_outcomes = {word: all(attempts) for word, attempts in word_buckets.items()}

    try:
        summary = _record_vocab_submission(profile_key, word_outcomes, quiz_id=quiz_id)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except RuntimeError as error:
        return jsonify(error=str(error)), 500

    return jsonify(status='received', profile_key=profile_key, processed_words=len(word_outcomes), **summary)


@app.route('/demo_status')
def demo_status():
    connection_type = request.args.get('type', default=None)

    if connection_type not in ["FIX", "MQ", "SFTP", "ALL"]:
        return jsonify(error="Invalid connection type. Allowed values are FIX, MQ, SFTP, ALL."), 400

    return jsonify(message=f'All your {"" if connection_type == "ALL" else connection_type} connections are up and running')


@app.route('/demo_details')
def demo_details():
    connection_id = request.args.get('id', default=None)

    if not connection_id:
        return jsonify(error="ID parameter is required"), 400

    current_time = datetime.utcnow()
    random_minutes = random.randint(1, 20)
    last_connection_time = current_time - timedelta(minutes=random_minutes)

    return jsonify(message=f"Connection {connection_id} is up", lastConnectionTime=last_connection_time.isoformat() + "Z")


if __name__ == '__main__':
    app.run(debug=True)
