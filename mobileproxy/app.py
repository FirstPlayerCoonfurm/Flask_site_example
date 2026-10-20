from flask import Flask, render_template
from admin import admin_bp

app = Flask(__name__)
app.secret_key = 'change_this_to_random_secret'  # для сессий

# Регистрируем blueprint админки
app.register_blueprint(admin_bp)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tariffs')
def tariffs():
    return render_template('tariffs.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)