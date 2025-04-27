from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import pandas as pd
import random
import os

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# MongoDB Atlas connection
client = MongoClient("mongodb+srv://aarya:aarya123@cluster0.n4p9pyd.mongodb.net/mindmaze_db?retryWrites=true&w=majority&appName=Cluster0")
db = client['mindmaze_db']

# Collections
users_col = db['users']
quizzes_col = db['quizzes']
results_col = db['results']

# Routes
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        existing_user = users_col.find_one({'username': username})
        if existing_user:
            flash('Username already exists.')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        users_col.insert_one({'username': username, 'password': hashed_password, 'role': role})
        flash('Signup successful! Please login.')
        return redirect(url_for('home'))

    return render_template('signup.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    user = users_col.find_one({'username': username})

    if user and check_password_hash(user['password'], password):
        session['username'] = username
        session['role'] = user['role']

        if user['role'] == 'conductor':
            return redirect(url_for('conductor_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    else:
        flash('Invalid credentials!')
        return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/conductor/dashboard')
def conductor_dashboard():
    if 'username' not in session or session['role'] != 'conductor':
        return redirect(url_for('home'))
    return render_template('conductor_dashboard.html')

@app.route('/conductor/upload_csv', methods=['GET', 'POST'])
def upload_csv():
    if 'username' not in session or session['role'] != 'conductor':
        return redirect(url_for('home'))

    if request.method == 'POST':
        file = request.files['file']
        quiz_code = request.form['quiz_code']
        num_questions = int(request.form['num_questions'])
        total_time = int(request.form['total_time'])

        if not file:
            flash('No file uploaded!')
            return redirect(url_for('conductor_dashboard'))

        existing_quiz = quizzes_col.find_one({'quiz_code': quiz_code})
        if existing_quiz:
            flash('Quiz code already exists! Please use a different code.')
            return redirect(url_for('conductor_dashboard'))

        df = pd.read_csv(file)
        all_questions = df.to_dict('records')

        if num_questions > len(all_questions):
            flash('Number of questions requested exceeds available questions!')
            return redirect(url_for('conductor_dashboard'))

        selected_questions = random.sample(all_questions, num_questions)

        quizzes_col.insert_one({
            'conductor': session['username'],
            'quiz_name': file.filename.split('.')[0],
            'quiz_code': quiz_code,
            'questions': selected_questions,
            'total_time': total_time
        })

        flash('Quiz created successfully from CSV!')
        return redirect(url_for('conductor_dashboard'))

    return redirect(url_for('conductor_dashboard'))

@app.route('/student/dashboard')
def student_dashboard():
    if 'username' not in session or session['role'] != 'student':
        return redirect(url_for('home'))
    return render_template('student_dashboard.html')

@app.route('/student/join_quiz', methods=['POST'])
def student_join_quiz():
    if 'username' not in session or session['role'] != 'student':
        return redirect(url_for('home'))

    quiz_code = request.form['quiz_code'].strip()
    quiz = quizzes_col.find_one({'quiz_code': quiz_code})

    if not quiz:
        flash('Invalid Quiz Code! Please try again.')
        return redirect(url_for('student_dashboard'))

    return redirect(url_for('attempt_quiz', quiz_id=quiz['_id']))

@app.route('/quiz/<quiz_id>', methods=['GET', 'POST'])
def attempt_quiz(quiz_id):
    quiz = quizzes_col.find_one({'_id': ObjectId(quiz_id)})

    if request.method == 'POST':
        correct = 0
        for idx, question in enumerate(quiz['questions']):
            selected = request.form.get(f'question_{idx}')
            if selected is not None:
                selected = int(selected)
                correct_option = int(question['correct_option'])
                if selected == correct_option:
                    correct += 1

        total = len(quiz['questions'])
        score = (correct / total) * 100

        result = {
            'quiz_id': str(quiz['_id']),
            'student_username': session['username'],  # ✅ saving student username
            'score': score
        }
        results_col.insert_one(result)

        flash(f'Quiz submitted successfully! Your Score: {score:.2f}%')
        return redirect(url_for('student_dashboard'))

    return render_template('attempt_quiz.html', quiz=quiz)


@app.route('/conductor/results', methods=['GET', 'POST'])
def conductor_results():
    if 'username' not in session or session['role'] != 'conductor':
        return redirect(url_for('home'))

    if request.method == 'POST':
        quiz_code = request.form['quiz_code'].strip()
        quiz = quizzes_col.find_one({'quiz_code': quiz_code})

        if not quiz:
            flash('Quiz code not found! Please check again.')
            return redirect(url_for('conductor_results'))

        quiz_id = str(quiz['_id'])
        results = list(results_col.find({'quiz_id': quiz_id}))

        # Sort by score descending
        sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)

        return render_template('view_results.html', results=sorted_results, quiz_code=quiz_code)

    return render_template('search_quiz_code.html')


@app.route('/result/<quiz_id>')
def view_result(quiz_id):
    if 'username' not in session or session['role'] != 'student':
        return redirect(url_for('home'))

    result = results_col.find_one({'student': session['username'], 'quiz_id': quiz_id})
    return render_template('result.html', result=result)

if __name__ == '__main__':
    app.run(debug=True)
@app.route('/conductor/delete_quiz', methods=['GET', 'POST'])
def delete_quiz():
    if 'username' not in session or session['role'] != 'conductor':
        return redirect(url_for('home'))

    if request.method == 'POST':
        quiz_code = request.form['quiz_code'].strip()
        quiz = quizzes_col.find_one({'quiz_code': quiz_code})

        if not quiz:
            flash('Quiz not found! Please check the code.')
            return redirect(url_for('delete_quiz'))

        # Delete Quiz
        quizzes_col.delete_one({'quiz_code': quiz_code})

        # Delete Results
        results_col.delete_many({'quiz_id': str(quiz['_id'])})

        flash(f'Quiz "{quiz_code}" and all related records deleted successfully.')
        return redirect(url_for('conductor_dashboard'))

    return render_template('delete_quiz.html')
