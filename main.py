
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_muy_segura_123'

# Configuración de la base de datos
DATABASE = 'forum.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                author_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (author_id) REFERENCES users (id)
            );
            
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                post_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id),
                FOREIGN KEY (author_id) REFERENCES users (id)
            );
        ''')
        
        # Crear usuario moderador por defecto
        moderator_exists = db.execute('SELECT id FROM users WHERE username = ?', ('moderador',)).fetchone()
        if not moderator_exists:
            password_hash = generate_password_hash('admin123')
            db.execute(
                'INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('moderador', 'mod@foro.com', password_hash, 'moderator')
            )
            db.commit()
        db.close()

@app.route('/')
def index():
    db = get_db()
    posts = db.execute('''
        SELECT p.id, p.title, p.content, p.created_at, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        ORDER BY p.created_at DESC
    ''').fetchall()
    db.close()
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if not username or not email or not password:
            flash('Todos los campos son obligatorios')
            return render_template('register.html')
        
        db = get_db()
        
        # Verificar si el usuario ya existe
        if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('El nombre de usuario ya existe')
            db.close()
            return render_template('register.html')
        
        if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
            flash('El email ya está registrado')
            db.close()
            return render_template('register.html')
        
        # Crear nuevo usuario
        password_hash = generate_password_hash(password)
        db.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        db.commit()
        db.close()
        
        flash('Registro exitoso! Ahora puedes iniciar sesión')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        db.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f'Bienvenido, {username}!')
            return redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión exitosamente')
    return redirect(url_for('index'))

@app.route('/new_post', methods=['GET', 'POST'])
def new_post():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para crear un post')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        if not title or not content:
            flash('El título y contenido son obligatorios')
            return render_template('new_post.html')
        
        db = get_db()
        db.execute(
            'INSERT INTO posts (title, content, author_id) VALUES (?, ?, ?)',
            (title, content, session['user_id'])
        )
        db.commit()
        db.close()
        
        flash('Post creado exitosamente!')
        return redirect(url_for('index'))
    
    return render_template('new_post.html')

@app.route('/post/<int:post_id>')
def view_post(post_id):
    db = get_db()
    post = db.execute('''
        SELECT p.id, p.title, p.content, p.created_at, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        WHERE p.id = ?
    ''', (post_id,)).fetchone()
    
    comments = db.execute('''
        SELECT c.id, c.content, c.created_at, u.username 
        FROM comments c 
        JOIN users u ON c.author_id = u.id 
        WHERE c.post_id = ? 
        ORDER BY c.created_at ASC
    ''', (post_id,)).fetchall()
    
    db.close()
    
    if not post:
        flash('Post no encontrado')
        return redirect(url_for('index'))
    
    return render_template('post.html', post=post, comments=comments)

@app.route('/post/<int:post_id>/comment', methods=['POST'])
def add_comment(post_id):
    if 'user_id' not in session:
        flash('Debes iniciar sesión para comentar')
        return redirect(url_for('login'))
    
    content = request.form['content']
    if not content:
        flash('El comentario no puede estar vacío')
        return redirect(url_for('view_post', post_id=post_id))
    
    db = get_db()
    db.execute(
        'INSERT INTO comments (content, post_id, author_id) VALUES (?, ?, ?)',
        (content, post_id, session['user_id'])
    )
    db.commit()
    db.close()
    
    flash('Comentario agregado exitosamente!')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/delete_post/<int:post_id>')
def delete_post(post_id):
    if 'user_id' not in session or session.get('role') != 'moderator':
        flash('No tienes permisos para eliminar posts')
        return redirect(url_for('index'))
    
    db = get_db()
    db.execute('DELETE FROM comments WHERE post_id = ?', (post_id,))
    db.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    db.commit()
    db.close()
    
    flash('Post eliminado exitosamente')
    return redirect(url_for('index'))

@app.route('/delete_comment/<int:comment_id>/<int:post_id>')
def delete_comment(comment_id, post_id):
    if 'user_id' not in session or session.get('role') != 'moderator':
        flash('No tienes permisos para eliminar comentarios')
        return redirect(url_for('view_post', post_id=post_id))
    
    db = get_db()
    db.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    db.commit()
    db.close()
    
    flash('Comentario eliminado exitosamente')
    return redirect(url_for('view_post', post_id=post_id))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
