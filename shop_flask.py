from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime
from functools import wraps
from flask_login import login_required
import pandas as pd
from flask import send_file
from io import BytesIO


# ------------------------
# Flask App Setup
# ------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///soundbox_repair_shop.db'

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ------------------------
# Models
# ------------------------
class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    device = db.Column(db.String(100), nullable=False)
    problem = db.Column(db.String(200), nullable=False)
    appointment_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="Pending")
    token_number = db.Column(db.String(36), unique=True, nullable=False)


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    daily_appointment_limit = db.Column(db.Integer, default=10)


# '''

# ------------------------
# Flask-Login Config
# ------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


# ------------------------
# Admin Access Decorator
# ------------------------
def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access admin dashboard.", "warning")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


    
# '''


# ------------------------
# Public Routes (Customers)
# ------------------------
@app.route('/')
def home():
    return render_template('home_shop.html')


@app.route('/book_appointment', methods=['GET', 'POST'])
def book_appointment():
    # Default values for the form
    customer_name = request.args.get('customer_name', '')
    phone_number = request.args.get('phone_number', '')
    address = request.args.get('address', '')
    device = request.args.get('device', '')
    problem = request.args.get('problem', '')
    appointment_date = request.args.get('appointment_date', '')
    reschedule_id = request.args.get('reschedule_id', None)

    if request.method == 'POST':
        # Extract the form data
        customer_name = request.form['customer_name']
        phone_number = request.form['phone_number']
        address = request.form['address']
        device = request.form['device']
        problem = request.form['problem']
        appointment_date_str = request.form['appointment_date']

        try:
            appointment_date = datetime.strptime(appointment_date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            return render_template('status_result.html', error="Invalid date format.")

        # Check daily limit
        settings = Settings.query.first()
        daily_limit = settings.daily_appointment_limit if settings else 10
        appointments_count = Appointment.query.filter(Appointment.appointment_date.like(f'{appointment_date.date()}%')).count()

        if appointments_count >= daily_limit:
            return render_template('status_result.html', error="Appointment limit reached for this day.")

        token_number = str(uuid.uuid4())
        new_appointment = Appointment(
            customer_name=customer_name,
            phone_number=phone_number,
            address=address,
            device=device,
            problem=problem,
            appointment_date=appointment_date,
            token_number=token_number
        )

        # If reschedule_id is passed, update the existing appointment
        if reschedule_id:
            existing_appointment = Appointment.query.get(reschedule_id)
            if existing_appointment:
                existing_appointment.customer_name = customer_name
                existing_appointment.phone_number = phone_number
                existing_appointment.address = address
                existing_appointment.device = device
                existing_appointment.problem = problem
                existing_appointment.appointment_date = appointment_date
                existing_appointment.token_number = token_number
                db.session.commit()
                return redirect(url_for('check_status'))  # Redirect to the status page after reschedule
        else:
            db.session.add(new_appointment)
            db.session.commit()

        return render_template('status_result.html', appointment=[new_appointment])

    return render_template('book_appointment.html', customer_name=customer_name, phone_number=phone_number, address=address, device=device, problem=problem, appointment_date=appointment_date)

@app.route('/check_status', methods=['GET', 'POST'])
def check_status():
    if request.method == 'POST':
        phone_number = request.form['phone_number']
        appointments = Appointment.query.filter_by(phone_number=phone_number).all()
        if appointments:
            return render_template('status_result.html', appointment=appointments)
        else:
            return render_template('status_result.html', error="No appointments found.")
    return render_template('check_status.html')


@app.route('/appointment/cancel/<int:id>', methods=['POST'])
def cancel_appointment(id):
    appt = Appointment.query.get_or_404(id)
    if appt.status == 'Pending':
        appt.status = 'Cancelled'
        db.session.commit()
        flash('Appointment cancelled successfully.', 'success')
    else:
        flash('Only pending appointments can be cancelled.', 'warning')
    return redirect(url_for('check_status'))





# '''

# ------------------------
# Admin Authentication
# ------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid credentials", "danger")
            return render_template('admin_login.html')
    return render_template('admin_login.html')


@app.route('/admin/logout')
@owner_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))


    

# ------------------------
# Admin Dashboard & Actions
# ------------------------
@app.route('/admin', methods=['GET'])
@owner_required
def admin_dashboard():
    status_filter = request.args.get('status')
    date_filter = request.args.get('date')
    # query = Appointment.query
    query = Appointment.query.filter(Appointment.status != "Cancelled")

    if status_filter:
        query = query.filter(Appointment.status == status_filter)
    if date_filter and date_filter != 'None':
        query = query.filter(Appointment.appointment_date.like(f'{date_filter}%'))

    page = request.args.get('page', 1, type=int)
    sort_order = request.args.get('sort', 'desc')

    if sort_order == 'asc':
        query = query.order_by(Appointment.id.asc())
    else:
        query = query.order_by(Appointment.id.desc())

    appointments = query.paginate(page=page, per_page=10, error_out=False)

    # Format date/time
    for a in appointments.items:
        a.formatted_date = a.appointment_date.strftime("%d-%m-%Y")
        a.formatted_time = a.appointment_date.strftime("%I:%M %p")

    return render_template('admin_dashboard.html', appointments=appointments, status_filter=status_filter, date_filter=date_filter, sort_order=sort_order)




# ------------------------
# Admin Excel Export
# ------------------------
@app.route('/admin/export', methods=['GET'])
@owner_required
def export_appointments():
    appointments = Appointment.query.all()
    
    # Prepare the data for Excel export
    data = []
    for appointment in appointments:
        data.append({
            'Customer Name': appointment.customer_name,
            'Phone Number': appointment.phone_number,
            'Address': appointment.address,
            'Device': appointment.device,
            'Problem': appointment.problem,
            'Appointment Date': appointment.appointment_date.strftime('%d-%m-%Y %I:%M %p'),
            'Status': appointment.status,
            'Token Number': appointment.token_number
        })

    # Create DataFrame
    df = pd.DataFrame(data)

    # Save DataFrame to a BytesIO buffer
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Appointments')
    
    output.seek(0)
    
    # Return the file as an attachment
    return send_file(output, as_attachment=True, download_name='appointments.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')














@app.route('/admin/update_status/<int:id>', methods=['POST'])
@owner_required
def update_status(id):
    appointment = Appointment.query.get_or_404(id)
    appointment.status = request.form['status']
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete/<int:id>', methods=['POST'])
@owner_required
def delete_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    db.session.delete(appointment)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@owner_required
def update_settings():
    settings = Settings.query.first()
    if request.method == 'POST':
        new_limit = int(request.form['daily_appointment_limit'])
        if settings:
            settings.daily_appointment_limit = new_limit
        else:
            settings = Settings(daily_appointment_limit=new_limit)
            db.session.add(settings)
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('update_settings.html', settings=settings)


# ------------------------
# Run App
# ------------------------
if __name__ == '__main__':
    app.run(debug=True)


