Smart Diet Planner

 It is a personalized AI-powered diet planning and meal analysis web app built with **Flask**, helping users plan, analyze, and optimize their daily meals based on their nutritional goals.

Features
**1. User Authentication**
- Secure registration and login system using Flask-Login & password hashing.
**2. Diet Plan Generator**
- Generates personalized meal plans based on weight, height, and nutritional targets.
- Automatically calculates BMI and suggests balanced diet options.
**3. Meal Analyzer**
- Analyze selected food and drink items for calorie, protein, carb, and fat content.
- Supports multiple food items per meal and suggests alternatives when nutrients are lacking.
**4. Dashboard**
- Manage, view, and delete diet plans with one click.
- Quick access to meal analysis tools.
**5. Nutrient Suggestions**
- Suggests foods or drinks that match the user’s nutrient deficiencies.

Tech Stack

| Component | Technology |
|------------|-------------|
| **Backend** | Flask (Python) |
| **Frontend** | HTML, Bootstrap, Jinja2 |
| **Database** | SQLite (via SQLAlchemy ORM) |
| **Authentication** | Flask-Login |
| **Data Source** | Indian_Food_Nutrition_Processed.csv |
| **Machine Learning (optional)** | Scikit-learn / custom nutrient analyzer logic |
