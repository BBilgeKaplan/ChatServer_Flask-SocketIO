from flask import Flask, render_template, request, send_file, session, redirect, url_for, send_from_directory
from flask_socketio import join_room, leave_room, send, SocketIO
import random
import os
from string import ascii_uppercase


app = Flask(__name__)           # Flask uygulamasını başlatır
app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app)        # Flask-SocketIO'yu uygulamaya entegre eder

rooms = {}

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER     # Flask uygulamasına yükleme klasörünü kaydeder
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'wav', '.mp3'}

# Rastgele ve benzersiz oda kodları oluşturmak için bir fonksiyon
def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)
        
        if code not in rooms:   # Oluşturulan kodun odalar listesinde olup olmadığını kontrol eder
            break               # Eğer odalar listesinde yoksa döngüyü sonlandırır ve kodu döndürür
    return code

# POST isteği alındığında, kullanıcı adı, oda kodu ve diğer bilgileri alır
@app.route("/", methods=["POST", "GET"])
def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        # Eğer kullanıcı adı girilmemişse, hata mesajı gösterir ve ana sayfayı yeniden yükler
        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name)

        # Eğer kullanıcı bir odaya katılmak istiyorsa ve oda kodu girilmemişse, hata mesajı gösterir ve ana sayfayı yeniden yükler
        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)
        
        room = code
        # Eğer kullanıcı yeni bir oda oluşturmak istiyorsa
        if create != False:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, "messages": []}
        
        # Eğer kullanıcı var olan bir odaya katılmak istiyorsa ve oda kodu odalar listesinde yoksa, hata mesajı gösterir ve ana sayfayı yeniden yükler
        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code, name=name)
        
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room")) # Kullanıcıyı ilgili odaya yönlendirir

    # GET isteği alındığında, ana sayfayı render eder
    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room") # Oturumdan oda kodunu alır
    # Eğer oda kodu yoksa, kullanıcı adı yoksa veya oda kodu odalar listesinde yoksa, ana sayfaya yönlendirir
    if room is None or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))

     # Oda kodunu ve odaya ait mesajları içeren şablonu render eder
    return render_template("room.html", code=room, messages=rooms[room]["messages"])

@socketio.on("message")
def message(data):
    room = session.get("room") # Oturumdan oda kodunu alır
    if room not in rooms: # Eğer kullanıcı bir odaya katılmadıysa, mesaj işlemini iptal eder
        return 
    
    content = {
        "name": session.get("name"), # Mesajı gönderenin kullanıcı adını alır
        "message": data["data"] # Gönderilen mesajı alır
    }
    send(content, to=room) # Odaya mesajı gönderir
    rooms[room]["messages"].append(content) # Odadaki mesaj listesine mesajı ekler
    print(f"{session.get('name')} said: {data['data']}") # Konsola mesajı yazdırır

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")

    # Eğer oda kodu veya kullanıcı adı yoksa, işlemi sonlandırır
    if not room or not name:
        return
     
     # Eğer kullanıcı bir odaya katılmadıysa, odayı terk eder ve işlemi sonlandırır
    if room not in rooms:
        leave_room(room)
        return
    
    join_room(room) # Kullanıcıyı ilgili odaya katılır
    send({"name": name, "message": "has entered the room"}, to=room) # Odadaki diğer kullanıcılara katılma mesajı gönderir
    rooms[room]["members"] += 1 # Odadaki üye sayısını artırır
    print(f"{name} joined room {room}") # Konsola katılma mesajını yazdırır

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0: # Eğer odadaki üye sayısı sıfırsa
            del rooms[room]  # Odanın bilgilerini siler
    
     # Odadaki diğer kullanıcılara ayrılma mesajı gönderir
    send({"name": name, "message": "has left the room"}, to=room)
    print(f"{name} has left the room {room}")


# Dosyayı yükle ve kaydet
@app.route('/upload', methods=['POST'])
def upload():
    room = session.get("room")
    if 'Dosya' not in request.files: # Eğer dosya yüklenmediyse hata mesajı döndürür
        return 'No file part'
    dosya = request.files['Dosya'] # Yüklenen dosyayı alır
    if dosya.filename == '': # Eğer dosya seçilmediyse hata mesajı döndürür
        return 'No selected file'

    # Yüklenen dosyayı kaydet
    dosya_yolu = os.path.join(app.config['UPLOAD_FOLDER'], dosya.filename)  # Dosya yolunu oluşturur
    dosya.save(dosya_yolu) # Dosyayı belirtilen yola kaydeder
    dosya_adi = dosya.filename  # Dosya adını alır

    content = {
        "name": session.get("name"),
        "message": dosya_yolu
    }

    # Dosyanın URL'sini diğer istemcilere gönder
    socketio.emit('dosya_geldi', {'name': session.get("name"), 'dosya_adi': dosya_adi, 'dosya_yolu': dosya_yolu}, to=room)
    rooms[room]["messages"].append(content)  # Odadaki mesaj listesine mesajı ekler
    print(f"{session.get('name')} upload a file: {dosya_adi}")

    return 'File uploaded successfully' # Başarı mesajı döndürür

@app.route('/uploads/<name>')
def download_file(name):
    return send_from_directory(app.config["UPLOAD_FOLDER"], name)
# Bu fonksiyon, istemci tarafından belirtilen bir dosyanın indirilmesini sağlar. name parametresi, indirilecek dosyanın adını temsil eder. send_from_directory fonksiyonu, belirtilen dizinden belirtilen dosyayı istemciye gönderir. Bu sayede istemci, sunucudaki belirli bir dizindeki dosyaya erişebilir ve indirebilir. 

if __name__ == "__main__":
    socketio.run(app, debug=True)