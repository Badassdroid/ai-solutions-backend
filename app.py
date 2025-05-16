import os
import csv
import io
import jwt as pyjwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import traceback

# Load environment variables
load_dotenv()

# Validate required environment variables
required_vars = ["SECRET_KEY", "DATABASE_URL", "ADMIN_PASSWORD"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

db = SQLAlchemy(app)

# Define Inquiry model
class Inquiry(db.Model):
    __tablename__ = 'inquiries'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50))
    company = db.Column(db.String(100))
    country = db.Column(db.String(100))
    job_title = db.Column(db.String(100))
    job_details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# Define Review model
class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    review = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # Ensure rating is between 1 and 5
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Define Newsletter model
class Newsletter(db.Model):
    __tablename__ = 'newsletters'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# Token validation decorator
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            abort(401, description="Authorization header is missing")
            
        try:
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                abort(401, description="Invalid authorization scheme")
                
            payload = pyjwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            if not payload.get("admin"):
                abort(403, description="Admin privileges required")
                
        except pyjwt.ExpiredSignatureError:
            abort(401, description="Token has expired")
        except pyjwt.InvalidTokenError as e:
            abort(401, description=f"Invalid token: {str(e)}")
        except ValueError:
            abort(401, description="Invalid authorization header format")
            
        return f(*args, **kwargs)
    return decorated

# Routes
@app.route("/api/inquiries", methods=["POST"])
def create_inquiry():
    required_fields = ["name", "email"]
    data = request.get_json()
    
    if not data:
        abort(400, description="No data provided")
    
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        abort(400, description=f"Missing required fields: {', '.join(missing_fields)}")
    
    try:
        inquiry = Inquiry(
            name=data.get("name"),
            email=data.get("email"),
            phone=data.get("phone"),
            company=data.get("company"),
            country=data.get("country"),
            job_title=data.get("job_title"),
            job_details=data.get("job_details")
        )
        db.session.add(inquiry)
        db.session.commit()
        return jsonify({"message": "Inquiry submitted successfully"}), 201
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to create inquiry: {str(e)}")

@app.route("/api/inquiries", methods=["GET"])
@admin_required
def get_inquiries():
    try:
        inquiries = Inquiry.query.order_by(Inquiry.timestamp.desc()).all()
        return jsonify([{
            "id": i.id,
            "name": i.name,
            "email": i.email,
            "phone": i.phone,
            "company": i.company,
            "country": i.country,
            "job_title": i.job_title,
            "job_details": i.job_details,
            "timestamp": i.timestamp.isoformat()
        } for i in inquiries])
    except Exception as e:
        abort(500, description=f"Failed to retrieve inquiries: {str(e)}")

@app.route("/api/export", methods=["GET"])
@admin_required
def export_inquiries():
    try:
        inquiries = Inquiry.query.order_by(Inquiry.timestamp.desc()).all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Name", "Email", "Phone", "Company", 
            "Country", "Job Title", "Job Details", "Timestamp"
        ])
        
        for i in inquiries:
            writer.writerow([
                i.id, i.name, i.email, i.phone, i.company,
                i.country, i.job_title, i.job_details, i.timestamp.isoformat()
            ])
            
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"inquiries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    except Exception as e:
        abort(500, description=f"Failed to export inquiries: {str(e)}")

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data or "username" not in data or "password" not in data:
        abort(400, description="Username and password are required")
    
    # Validate username and password
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")
    
    if data["username"] != admin_username or data["password"] != admin_password:
        abort(401, description="Invalid credentials")
    
    expiration_time = datetime.utcnow() + timedelta(hours=1)
    token = pyjwt.encode(
        {
            "admin": True,
            "username": data["username"],
            "exp": expiration_time
        },
        app.config['SECRET_KEY'],
        algorithm="HS256"
    )
    
    return jsonify({
        "token": token,
        "expires_at": expiration_time.isoformat(),
        "dashboard_url": "/admin"
    })

# Route to submit a review
@app.route("/api/reviews", methods=["POST"])
def submit_review():
    data = request.get_json()
    if not data or "name" not in data or "company" not in data or "review" not in data or "rating" not in data:
        abort(400, description="Name, company, review, and rating are required")

    if not (1 <= data["rating"] <= 5):
        abort(400, description="Rating must be between 1 and 5")

    try:
        review = Review(
            name=data["name"],
            company=data["company"],
            review=data["review"],
            rating=data["rating"]
        )
        db.session.add(review)
        db.session.commit()
        return jsonify({"message": "Review submitted successfully"}), 201
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to submit review: {str(e)}")

# Route to get all reviews
@app.route("/api/reviews", methods=["GET"])
def get_reviews():
    try:
        reviews = Review.query.order_by(Review.timestamp.desc()).all()
        return jsonify([{
            "id": r.id,
            "name": r.name,
            "company": r.company,
            "review": r.review,
            "rating": r.rating,
            "timestamp": r.timestamp.isoformat()
        } for r in reviews])
    except Exception as e:
        abort(500, description=f"Failed to retrieve reviews: {str(e)}")
        
# Route to submit a Newsletters subscription.
@app.route("/api/newsletters", methods=["POST"])
def create_newsletter():
    required_fields = ["name", "email"]
    data = request.get_json()
    
    if not data:
        abort(400, description="No data provided")
    
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        abort(400, description=f"Missing required fields: {', '.join(missing_fields)}")
    
    try:
        newsletter = Newsletter(
            name=data.get("name"),
            email=data.get("email")
        )
        db.session.add(newsletter)
        db.session.commit()
        return jsonify({"message": "Newsletter subscription submitted successfully"}), 201
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to create newsletter: {str(e)}")

@app.route("/api/newsletters", methods=["GET"])
@admin_required
def get_newsletters():
    try:
        newsletters = Newsletter.query.order_by(Newsletter.timestamp.desc()).all()
        return jsonify([{
            "id": i.id,
            "name": i.name,
            "email": i.email,
            "timestamp": i.timestamp.isoformat()
        } for i in newsletters])
    except Exception as e:
        abort(500, description=f"Failed to retrieve newsletters: {str(e)}")
# Add these new routes to your Flask application

# Route to delete an inquiry
@app.route("/api/inquiries/<int:inquiry_id>", methods=["DELETE"])
@admin_required
def delete_inquiry(inquiry_id):
    try:
        inquiry = Inquiry.query.get_or_404(inquiry_id)
        db.session.delete(inquiry)
        db.session.commit()
        return jsonify({"message": f"Inquiry {inquiry_id} deleted successfully"})
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to delete inquiry: {str(e)}")

# Route to update an inquiry
@app.route("/api/inquiries/<int:inquiry_id>", methods=["PUT"])
@admin_required
def update_inquiry(inquiry_id):
    data = request.get_json()
    if not data:
        abort(400, description="No data provided")
    
    try:
        inquiry = Inquiry.query.get_or_404(inquiry_id)
        
        # Update fields if provided
        if "name" in data:
            inquiry.name = data["name"]
        if "email" in data:
            inquiry.email = data["email"]
        if "phone" in data:
            inquiry.phone = data["phone"]
        if "company" in data:
            inquiry.company = data["company"]
        if "country" in data:
            inquiry.country = data["country"]
        if "job_title" in data:
            inquiry.job_title = data["job_title"]
        if "job_details" in data:
            inquiry.job_details = data["job_details"]
        
        db.session.commit()
        return jsonify({
            "id": inquiry.id,
            "name": inquiry.name,
            "email": inquiry.email,
            "phone": inquiry.phone,
            "company": inquiry.company,
            "country": inquiry.country,
            "job_title": inquiry.job_title,
            "job_details": inquiry.job_details,
            "timestamp": inquiry.timestamp.isoformat()
        })
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to update inquiry: {str(e)}")

# Route to delete a newsletter subscription
@app.route("/api/newsletters/<int:newsletter_id>", methods=["DELETE"])
@admin_required
def delete_newsletter(newsletter_id):
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        db.session.delete(newsletter)
        db.session.commit()
        return jsonify({"message": f"Newsletter subscription {newsletter_id} deleted successfully"})
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to delete newsletter subscription: {str(e)}")

# Route to update a newsletter subscription
@app.route("/api/newsletters/<int:newsletter_id>", methods=["PUT"])
@admin_required
def update_newsletter(newsletter_id):
    data = request.get_json()
    if not data:
        abort(400, description="No data provided")
    
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        
        # Update fields if provided
        if "name" in data:
            newsletter.name = data["name"]
        if "email" in data:
            newsletter.email = data["email"]
        
        db.session.commit()
        return jsonify({
            "id": newsletter.id,
            "name": newsletter.name,
            "email": newsletter.email,
            "timestamp": newsletter.timestamp.isoformat()
        })
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to update newsletter subscription: {str(e)}")

# Route to delete a review
@app.route("/api/reviews/<int:review_id>", methods=["DELETE"])
@admin_required
def delete_review(review_id):
    try:
        review = Review.query.get_or_404(review_id)
        db.session.delete(review)
        db.session.commit()
        return jsonify({"message": f"Review {review_id} deleted successfully"})
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to delete review: {str(e)}")

# Route to update a review
@app.route("/api/reviews/<int:review_id>", methods=["PUT"])
@admin_required
def update_review(review_id):
    data = request.get_json()
    if not data:
        abort(400, description="No data provided")
    
    try:
        review = Review.query.get_or_404(review_id)
        
        # Update fields if provided
        if "name" in data:
            review.name = data["name"]
        if "company" in data:
            review.company = data["company"]
        if "review" in data:
            review.review = data["review"]
        if "rating" in data:
            if not (1 <= data["rating"] <= 5):
                abort(400, description="Rating must be between 1 and 5")
            review.rating = data["rating"]
        
        db.session.commit()
        return jsonify({
            "id": review.id,
            "name": review.name,
            "company": review.company,
            "review": review.review,
            "rating": review.rating,
            "timestamp": review.timestamp.isoformat()
        })
    except Exception as e:
        db.session.rollback()
        abort(500, description=f"Failed to update review: {str(e)}")


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(500)
def handle_error(e):
    response = {
        "error": e.name,
        "message": e.description
    }
    if e.code == 500:
        print("⚠️ Server error occurred:\n", traceback.format_exc())
    return jsonify(response), e.code
@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "AI Solutions Backend API is running."})


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=os.getenv("FLASK_DEBUG", "False").lower() == "true")

