import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from ml.meal_recommender import recommend_meals
from ml.nutrient_analyzer import analyze_selected_meals,get_all_foods,analyze_meal_text

load_dotenv()  # loads .env if present
APP_ID = os.getenv("NUTRITIONIX_APP_ID")
API_KEY = os.getenv("NUTRITIONIX_API_KEY")


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# ---------- Models ----------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(150), unique=True)
    password_hash = db.Column(db.String(200))

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class DietPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(200))
    meals_count = db.Column(db.Integer)
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    target_calories = db.Column(db.Integer)
    target_protein = db.Column(db.Float)
    target_carbs = db.Column(db.Float)
    target_fat = db.Column(db.Float)
    # store recommended meal summary as JSON string or text
    plan_json = db.Column(db.Text)

with app.app_context():
 db.create_all()

# ---------- Login ----------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- Routes ----------
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please log in.', 'danger')
            return redirect(url_for('login'))
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Registered and logged in!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email or password', 'danger')
            return redirect(url_for('login'))
        login_user(user)
        flash('Logged in successfully.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    plans = DietPlan.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', plans=plans)

@app.route('/delete_plan/<int:plan_id>', methods=['POST'])
@login_required
def delete_plan(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    flash('Diet plan deleted successfully.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/create_plan', methods=['GET','POST'])
@login_required
def create_plan():
    if request.method == 'POST':
        name = request.form.get('plan_name') or 'My Plan'
        meals_count = int(request.form.get('meals_count', 3))
        weight = float(request.form.get('user_weight', 70))
        height = float(request.form.get('user_height', 170))
        # nutrient targets
        target_calories = int(request.form.get('target_calories', 2000))
        target_protein = float(request.form.get('target_protein', 75))
        target_carbs = float(request.form.get('target_carbs', 250))
        target_fat = float(request.form.get('target_fat', 70))

        # call recommender - returns dict with meals
        recommendation = recommend_meals(
            meals_count=meals_count,
            weight=weight,
            height=height,
            target_calories=target_calories,
            target_protein=target_protein,
            target_carbs=target_carbs,
            target_fat=target_fat
        )

        plan = DietPlan(
            user_id=current_user.id,
            name=name,
            meals_count=meals_count,
            weight=weight,
            height=height,
            target_calories=target_calories,
            target_protein=target_protein,
            target_carbs=target_carbs,
            target_fat=target_fat,
            plan_json=str(recommendation)
        )
        db.session.add(plan)
        db.session.commit()
        flash('Plan created successfully', 'success')
        return render_template('view_plan.html', plan=recommendation, bmi=calculate_bmi(weight, height))
    # GET
    return render_template('create_plan.html')

@app.route('/view_plan/<int:plan_id>')
@login_required
def view_plan(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    # convert stored string back to dict safely (we stored via str(), so use eval carefully)
    try:
        plan_dict = eval(plan.plan_json)
    except Exception:
        plan_dict = {"error":"can't load plan"}
    bmi = calculate_bmi(plan.weight, plan.height)
    return render_template('view_plan.html', plan=plan_dict, bmi=bmi)

@app.route('/analyze_meals', methods=['GET', 'POST'])
@login_required
def analyze_meals_route():
    from ml.nutrient_analyzer import analyze_selected_meals, get_all_foods

    result = None
    all_foods = get_all_foods()
    meal_types = ["Breakfast", "Lunch", "Dinner", "Snack"]

    if request.method == 'POST':
        try:
            num_meals = int(request.form.get('num_meals', 1))
            selected_meals = []
            selected_drinks = []

            for i in range(num_meals):
                # ✅ Handle single or multiple food selections
                meal_foods = request.form.getlist(f'meal_food_{i}[]')
                meal_drink = request.form.get(f'meal_drink_{i}[]', '').strip()

                # Add selected foods (if any)
                for food in meal_foods:
                    if food and food.strip():
                        selected_meals.append(food.strip())

                # Add selected drink (if any)
                if meal_drink:
                    selected_drinks.append(meal_drink)

            # Debugging output (shows what Flask actually received)
            print("Selected meals:", selected_meals)
            print("Selected drinks:", selected_drinks)

            # ✅ Check that at least one food or drink is actually chosen
            if not any(selected_meals) and not any(selected_drinks):
                result = {"error": "Please select at least one food or drink item."}
            else:
                result = analyze_selected_meals(selected_meals, selected_drinks)

        except Exception as e:
            result = {"error": str(e)}

    return render_template(
        'analyze_meals.html',
        result=result,
        all_foods=all_foods,
        meal_types=meal_types
    )

@app.route('/food_search')
@login_required
def food_search_api():
    import pandas as pd
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify([])

    df = pd.read_csv("Indian_Food_Nutrition_Processed.csv")
    df.columns = [c.strip().lower() for c in df.columns]
    if "food" not in df.columns:
        df.rename(columns={"dish name": "food"}, inplace=True)

    results = df[df["food"].str.lower().str.contains(q, na=False)].head(10)
    data = results[['food', 'calories', 'protein', 'carbs', 'fat']].to_dict(orient='records')
    return jsonify(data)

# ---------- Utilities ----------
def calculate_bmi(weight_kg, height_cm):
    try:
        h_m = height_cm / 100.0
        bmi = weight_kg / (h_m * h_m)
        return round(bmi, 2)
    except Exception:
        return None

if __name__ == '__main__':
    # ensure DB exists
  with app.app_context():
     db.create_all()
  app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


# import pandas as pd
# from flask import Flask, render_template, request, redirect, url_for, session, flash
# import sqlite3
# import hashlib
# import numpy as np 

# # Import ML model logic (make sure ml_model.py is in the same directory)
# from ml_model import generate_diet_plan_lp, suggest_meals

# # --- Configuration & Initialization ---
# app = Flask(__name__)
# app.secret_key = 'a_very_secret_key_for_session_management'
# DATABASE = 'nutrition_app.db'
# CSV_FILE = 'Indian_Food_Nutrition_Processed.csv' 

# # Load and Preprocess Data (Done once)
# try:
#     FOOD_DATA = pd.read_csv(CSV_FILE)
# except FileNotFoundError:
#     print(f"FATAL ERROR: {CSV_FILE} not found. Ensure the dataset is in the same directory.")
#     exit()

# # Clean and rename columns for easy lookup by the ML model
# FOOD_DATA = FOOD_DATA.rename(columns={
#     'Dish Name': 'Dish_Name', 
#     'Calories (kcal)': 'Calories_kcal', 
#     'Carbohydrates (g)': 'Carbohydrates_g', 
#     'Protein (g)': 'Protein_g', 
#     'Fats (g)': 'Fats_g'
# })

# # CRITICAL FIX: Reset the index. This ensures the ML model's .loc[i, ...] calls work.
# FOOD_DATA.reset_index(drop=True, inplace=True)

# # Convert relevant columns to numeric, setting errors='coerce' for non-numeric data
# for col in FOOD_DATA.columns[1:]:
#     FOOD_DATA[col] = pd.to_numeric(FOOD_DATA[col], errors='coerce').fillna(0)


# # --- Database Utility Functions ---
# def get_db_connection():
#     conn = sqlite3.connect(DATABASE)
#     conn.row_factory = sqlite3.Row
#     return conn

# def init_db():
#     conn = get_db_connection()
#     # Create the users table if it doesn't exist
#     conn.execute("""
#         CREATE TABLE IF NOT EXISTS users (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             username TEXT UNIQUE NOT NULL,
#             password_hash TEXT NOT NULL,
#             weight_kg REAL,
#             height_cm REAL,
#             target_calories REAL,
#             target_protein REAL,
#             target_carbs REAL,
#             target_fats REAL
#         )
#     """)
#     conn.commit()
#     conn.close()

# # --- Core Utility Functions ---

# def calculate_bmi(weight_kg, height_cm):
#     """Calculates BMI (Body Mass Index). Height must be in meters."""
#     if height_cm > 0:
#         height_m = height_cm / 100
#         # Use simple Python math functions (instead of np.power) to avoid unnecessary complexity
#         return weight_kg / (height_m * height_m)
#     return 0

# def hash_password(password):
#     """Simple SHA-256 hash for password storage."""
#     return hashlib.sha256(password.encode()).hexdigest()

# def check_password(hashed_password, user_password):
#     """Check if the provided password matches the stored hash."""
#     return hashed_password == hash_password(user_password)
    
# def get_nutrients_from_meals(meal_list):
#     """
#     Calculates total nutrients from a list of dish names.
#     """
#     if not meal_list:
#         return {}
    
#     # Filter the DataFrame for the selected dishes
#     selected_meals_df = FOOD_DATA[FOOD_DATA['Dish_Name'].isin(meal_list)]
    
#     # Sum the nutrient columns (using cleaned column names)
#     nutrient_cols = ['Calories_kcal', 'Carbohydrates_g', 'Protein_g', 'Fats_g', 'Free Sugar (g)', 'Fibre (g)', 'Sodium (mg)', 'Calcium (mg)', 'Iron (mg)', 'Vitamin C (mg)', 'Folate (µg)']
#     total_nutrients = selected_meals_df[nutrient_cols].sum().to_dict()
    
#     # Format the keys for display
#     return {k.replace('_', ' ').replace('(g)', '').replace('(kcal)', '').strip(): v for k, v in total_nutrients.items()}


# # --- Flask Routes (No changes needed here, using existing logic) ---

# @app.route('/')
# def index():
#     if 'user_id' in session:
#         return redirect(url_for('dashboard'))
#     return render_template('index.html')

# @app.route('/register', methods=['GET', 'POST'])
# def register():
#     if request.method == 'POST':
#         username = request.form['username']
#         password = request.form['password']
#         hashed_pwd = hash_password(password)
        
#         conn = get_db_connection()
#         try:
#             conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
#                          (username, hashed_pwd))
#             conn.commit()
#             flash('Registration successful! Please log in.', 'success')
#             return redirect(url_for('login'))
#         except sqlite3.IntegrityError:
#             flash('Username already taken.', 'danger')
#             return render_template('register.html')
#         finally:
#             conn.close()
            
#     return render_template('register.html')

# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     if request.method == 'POST':
#         username = request.form['username']
#         password = request.form['password']
        
#         conn = get_db_connection()
#         user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
#         conn.close()
        
#         if user and check_password(user['password_hash'], password):
#             session['user_id'] = user['id']
#             flash('Login successful!', 'success')
#             return redirect(url_for('dashboard'))
#         else:
#             flash('Invalid credentials.', 'danger')
#             return render_template('login.html')
            
#     return render_template('login.html')

# @app.route('/logout')
# def logout():
#     session.pop('user_id', None)
#     flash('You have been logged out.', 'info')
#     return redirect(url_for('index'))

# @app.route('/dashboard')
# def dashboard():
#     if 'user_id' not in session:
#         return redirect(url_for('login'))
        
#     conn = get_db_connection()
#     user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
#     conn.close()
    
#     bmi = 0
#     if user['weight_kg'] and user['height_cm']:
#         bmi = calculate_bmi(user['weight_kg'], user['height_cm'])
    
#     return render_template('dashboard.html', user=user, bmi=round(bmi, 2))

# @app.route('/create_diet', methods=['GET', 'POST'])
# def create_diet():
#     if 'user_id' not in session:
#         return redirect(url_for('login'))
        
#     conn = get_db_connection()
#     user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
#     conn.close()
    
#     diet_plan = None
#     if request.method == 'POST':
#         try:
#             # 1. Update user profile and nutrient targets
#             weight = float(request.form['weight'])
#             height = float(request.form['height'])
#             num_meals = int(request.form['num_meals'])
#             target_calories = float(request.form['target_calories'])
#             target_protein = float(request.form['target_protein'])
#             target_carbs = float(request.form['target_carbs'])
#             target_fats = float(request.form['target_fats'])
            
#             conn = get_db_connection()
#             conn.execute("""
#                 UPDATE users SET 
#                 weight_kg = ?, height_cm = ?, target_calories = ?, 
#                 target_protein = ?, target_carbs = ?, target_fats = ?
#                 WHERE id = ?
#             """, (weight, height, target_calories, target_protein, target_carbs, target_fats, session['user_id']))
#             conn.commit()
#             conn.close()
            
#             # 2. Generate diet plan using the LP Model from ml_model.py
#             # CRITICAL: Pass FOOD_DATA to the ML model
#             diet_plan = generate_diet_plan_lp(num_meals, target_calories, target_protein, target_carbs, target_fats, FOOD_DATA)
            
#             if diet_plan is None:
#                 flash("Could not generate a feasible diet plan with the current goals. Try adjusting your nutrient targets.", 'warning')

#         except ValueError:
#             flash("Please enter valid numbers for all fields.", 'danger')
            
#     return render_template('create_diet.html', user=user, diet_plan=diet_plan)


# @app.route('/meal_logging', methods=['GET', 'POST'])
# def meal_logging():
#     if 'user_id' not in session:
#         return redirect(url_for('login'))
        
#     conn = get_db_connection()
#     user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
#     conn.close()
    
#     all_dishes = FOOD_DATA['Dish_Name'].tolist()
    
#     current_nutrients = None
#     suggestions = None
#     # Use standard suggested targets for suggestions comparison
#     target_nutrients = {
#          'Calories': user['target_calories'] or 2000, 
#          'Protein': user['target_protein'] or 100, 
#          'Carbohydrates': user['target_carbs'] or 220, 
#          'Fats': user['target_fats'] or 60,
#          'Fibre': 25, 
#          'Sodium': 1500,
#          'Calcium': 1000,
#          'Iron': 18,
#          'Vitamin C': 90,
#          'Folate': 400
#     }
    
#     if request.method == 'POST':
#         meals_taken = request.form.getlist('meals_taken')
        
#         # 1. Calculate nutrients from logged meals
#         current_nutrients = get_nutrients_from_meals(meals_taken)
        
#         # 2. Get suggestions to fill gaps (using model logic)
#         # CRITICAL: Pass FOOD_DATA to the ML model
#         suggestions = suggest_meals(current_nutrients, target_nutrients, FOOD_DATA)
        
#     return render_template('meal_logging.html', all_dishes=all_dishes, current_nutrients=current_nutrients, target_nutrients=target_nutrients, suggestions=suggestions)


# if __name__ == '__main__':
#     init_db()
#     print("Database initialized. Running application...")
#     app.run(debug=True)
