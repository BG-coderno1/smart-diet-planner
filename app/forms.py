from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, IntegerField, FloatField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange


class RegisterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(min=2, max=150)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, message="Use at least 8 characters.")])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])


class CreatePlanForm(FlaskForm):
    plan_name = StringField("Plan name", validators=[DataRequired(), Length(max=200)])
    meals_count = IntegerField("Number of meals", validators=[DataRequired(), NumberRange(min=1, max=8)])
    user_weight = FloatField("Weight (kg)", validators=[DataRequired(), NumberRange(min=20, max=400)])
    user_height = FloatField("Height (cm)", validators=[DataRequired(), NumberRange(min=80, max=250)])
    target_calories = IntegerField("Target calories", validators=[DataRequired(), NumberRange(min=800, max=6000)])
    target_protein = FloatField("Target protein (g)", validators=[DataRequired(), NumberRange(min=0, max=500)])
    target_carbs = FloatField("Target carbs (g)", validators=[DataRequired(), NumberRange(min=0, max=900)])
    target_fat = FloatField("Target fat (g)", validators=[DataRequired(), NumberRange(min=0, max=400)])


class MealTextForm(FlaskForm):
    meal_text = TextAreaField(
        "Describe your meal",
        validators=[DataRequired(), Length(max=1000)],
    )


class FoodPhotoForm(FlaskForm):
    photo = FileField(
        "Meal photo",
        validators=[
            FileRequired(message="Please choose a photo."),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Only JPG, PNG, or WEBP images are allowed."),
        ],
    )
