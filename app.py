from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, send, join_room
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    blocked_users = db.relationship('BlockedUser', backref='user', lazy=True)

class BlockedUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocked_user_id = db.Column(db.Integer, nullable=False)

# Chat room model
class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(100), nullable=False, unique=True)
    is_private = db.Column(db.Boolean, default=False)
    password = db.Column(db.String(150), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# Message model
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Admin check decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Bạn không có quyền truy cập trang này.')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# Create default admin account if it does not exist
def create_admin():
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin_user = User(username='admin', password=hashed_password, is_admin=True)
        db.session.add(admin_user)
        db.session.commit()
        print("Admin user created successfully!")

# Home page
@app.route('/')
@login_required
def home():
    return render_template('home.html', username=current_user.username)

# Login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Đăng nhập không thành công. Vui lòng kiểm tra thông tin đăng nhập.')

    return render_template('login.html')

# Registration page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username và mật khẩu không được để trống!')
            return redirect(url_for('register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username đã tồn tại!')
            return redirect(url_for('register'))

        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Đăng ký thành công! Bây giờ bạn có thể đăng nhập.')
        return redirect(url_for('login'))

    return render_template('register.html')

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Select room page
@app.route('/select_room')
@login_required
def select_room():
    rooms = Room.query.all()
    return render_template('select_room.html', rooms=rooms)

# Create room page
@app.route('/create_room', methods=['GET', 'POST'])
@login_required
def create_room():
    if request.method == 'POST':
        room_id = request.form.get('room_id')
        is_private = 'is_private' in request.form
        password = request.form.get('password') if is_private else None

        existing_room = Room.query.filter_by(room_id=room_id).first()
        if existing_room:
            flash('Phòng này đã tồn tại!')
            return redirect(url_for('create_room'))

        new_room = Room(room_id=room_id, is_private=is_private,
                        password=bcrypt.generate_password_hash(password).decode('utf-8') if password else None,
                        owner_id=current_user.id)
        db.session.add(new_room)
        db.session.commit()
        flash(f'Phòng {room_id} đã được tạo thành công!')
        return redirect(url_for('chat', room=room_id))

    return render_template('create_room.html')

# Chat room page
@app.route('/chat/<room>', methods=['GET', 'POST'])
@login_required
def chat(room):
    room_obj = Room.query.filter_by(room_id=room).first()

    if room_obj.is_private:
        if request.method == 'POST':
            password = request.form.get('password')
            if bcrypt.check_password_hash(room_obj.password, password):
                return render_template('chat.html', room=room)
            else:
                flash('Mật khẩu không chính xác.')
                return redirect(url_for('chat', room=room))
        else:
            return render_template('enter_password.html', room=room)
    else:
        return render_template('chat.html', room=room)

# Handle join room event
@socketio.on('join')
def handle_join(data):
    username = data['username']
    room = data['room']
    join_room(room)

    messages = Message.query.filter_by(room=room).order_by(Message.timestamp).all()
    for msg in messages:
        send(f'{msg.username}: {msg.message}', to=username)

    send(f'{username} đã tham gia phòng.', to=room)

# Handle message event
@socketio.on('message')
def handle_message(data):
    room = data['room']
    message = data['message']
    username = data['username']

    new_message = Message(room=room, username=username, message=message)
    db.session.add(new_message)
    db.session.commit()

    send(f'{username}: {message}', to=room)

# Admin page
@app.route('/admin')
@login_required
@admin_required
def admin():
    users = User.query.all()
    rooms = Room.query.all()
    return render_template('admin.html', users=users, rooms=rooms)

# Delete user account (Admin)
@app.route('/admin/delete_user/<int:user_id>')
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash('Người dùng đã bị xóa.')
    return redirect(url_for('admin'))

# Delete chat room (Admin)
@app.route('/admin/delete_room/<int:room_id>')
@login_required
@admin_required
def delete_room(room_id):
    room = Room.query.get(room_id)
    if room:
        db.session.delete(room)
        db.session.commit()
        flash('Phòng đã bị xóa.')
    return redirect(url_for('admin'))

# Change password
@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    
    if bcrypt.check_password_hash(current_user.password, current_password):
        current_user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()
        flash('Mật khẩu đã được đổi thành công!')
    else:
        flash('Mật khẩu hiện tại không chính xác.')
    
    return redirect(url_for('profile'))

# User profile management page
@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

# Block user
@app.route('/block_user/<int:user_id>')
@login_required
def block_user(user_id):
    if current_user.is_admin:
        blocked_user = BlockedUser(user_id=current_user.id, blocked_user_id=user_id)
        db.session.add(blocked_user)
        db.session.commit()
        flash('Người dùng đã bị chặn.')
    return redirect(url_for('admin'))

# Rate chat room
@app.route('/rate_chat/<room>', methods=['POST'])
@login_required
def rate_chat(room):
    rating = request.form['rating']
    # Save rating to database or process it
    flash('Cảm ơn bạn đã đánh giá phòng chat!')
    return redirect(url_for('chat', room=room))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if they do not exist
        create_admin()  # Create admin user if it does not exist
    socketio.run(app, debug=True)
