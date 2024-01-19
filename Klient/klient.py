from kivy.app import App
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.clock import Clock

import socket
import time
import threading
import pyaudio
import os
import string


CHUNK = 4096
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000

p = pyaudio.PyAudio()
stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                output=True,
                frames_per_buffer=CHUNK)

# Lista w której zapisane będą wszystkie nośniki pamięci użytkownika
drives = ['%s:' % d for d in string.ascii_uppercase if os.path.exists('%s:' % d)]


# Funkcja odpowiadająca za wysyłanie pliku dźwiękowego na serwer
def send_file(sock_comm,sock_file, filepath):  

    if filepath == '':
        return

    # odczytanie listy zakolejkowanych utworów w celu sprawdzenia obecności wysyłanego utworu
    receive_queue(sock_comm)   

    # wyłącznie przycisków GUI
    buttons_off()

    filename = filepath[3:].split('\\')[-1] 
    if filename[:-4] in application.queue or filename[:-4] == application.now_playing:
        print("Wysyłany utwór jest już w kolejce\nPrzerywam wysyłanie")
        buttons_on()
        return
    
    time.sleep(1)
    print("Rozpoczynam wysyłanie pliku")

    sock_comm.send(bytes("sending_song", "utf-8"))
    
    sock_file.send(bytes(filename[:-4], "utf-8")) # nazwa pliku bez rozszerzenia
    time.sleep(4)
    file = open(filepath, 'rb')
    audio_data = file.read()
    size = 5000
    send_data = [audio_data[i:i+size] for i in range(0, len(audio_data), size)]

    for data in send_data:
        sock_file.send(data)

    time.sleep(4)
    sock_file.send(bytes("end_of_upload", "utf-8"))
    print("Plik wysłano pomyślnie")
    file.close()
    filepath = ''

    # włączenie przycisków GUI
    buttons_on()


# Funkcja odbierająca dźwięk od serwera i odtwarzająca go
def recieve_and_play(sock):
    while True:
        try:
            sock.settimeout(3)
            data = sock.recv(10000)
            stream.write(data)
            sock.settimeout(None)
        except (socket.timeout, OSError):
            break


# Funkcja odbierająca kolejkę utworów od serwera
def receive_queue(sock):

    buttons_off()

    new_queue = b''
    sock.send(bytes("queue_req", "utf-8"))
    time.sleep(1)
    while True:
        try:
            sock.settimeout(6)
            new_queue += sock.recv(1024)
            sock.settimeout(None)
        except: break
    new_queue = new_queue.decode("utf-8").split(" | ")[:-1]

    if len(new_queue) > 0:
        application.now_playing = new_queue[0]
        application.queue = new_queue[1:]

    print("Odebrano kolejkę")
    for title in new_queue:
        print(title)

    buttons_on()


# Funkcja wysyłająca zmodyfikowaną kolejkę utworów
def send_updated_queue(sock, new_queue):

    buttons_off()

    sock.send(bytes("queue_upd", "utf-8"))
    time.sleep(5)
    sock.send(bytes("|" + " | ".join(new_queue), "utf-8"))

    buttons_on()


# Funkcja wysyłająca polecenie pominięcia granego utworu
def skip(sock):

    buttons_off()

    sock.send(bytes("skip_song", "utf-8"))
    time.sleep(4)

    buttons_on()


# Stylistyczna funkcja rozbicia tekstu na 2 linie (do wyświetlania tytułu w aplikacji)
def break_line(string_):
    if len(string_)>60:
        split_title = string_.split()
        split_title = ' '.join(split_title[:len(split_title)//2]) +"\n" \
                    + ' '.join(split_title[len(split_title)//2:])
        return split_title
    return string_


# Funkcja wyłączająca wszystkie przyciski w aplikacji
def buttons_off():
    application.ids.skip_button.disabled = True
    application.ids.request_title_button.disabled = True
    application.ids.request_queue_button.disabled = True
    application.ids.send_queue_button.disabled = True
    application.ids.send_file_button.disabled = True


# Funkcja włączająca wszystkie przyciski w aplikacji
def buttons_on():
    application.ids.skip_button.disabled = False
    application.ids.request_title_button.disabled = False
    application.ids.request_queue_button.disabled = False
    application.ids.send_queue_button.disabled = False
    application.ids.send_file_button.disabled = False



#-------------------GUI-----------------------

class RadioGUI(TabbedPanel):
    # ścieżka utworu do wysłania
    to_send = ''
    # tytuł aktualnie granego utworu
    now_playing = ''
    # lista utworów w kolejce bez aktuanie granego
    queue =  []

    global sock_command, sock_in_audio, sock_out_file


    def __init__(self, **kwargs):
        super(RadioGUI, self).__init__(**kwargs)
        Clock.schedule_interval(lambda dt: self.generate_queue(), 1)


    # Funkcje do obsługi przycisków w aplikacji:

    # Zamiana przeglądanego dysku w zakładce wysyłania pliku
    def switch_disc(self):
        # aktualnie wybrany dysk
        current = self.ids.filechooser.path[0:2]
        print("Aktualnie wybrany dysk: ", current)
        current_id = drives.index(current)
        if current_id == len(drives)-1:
            current_id = 0
        else:
            current_id += 1
        
        self.ids.filechooser.path = drives[current_id] + r'\\'
        self.ids.discswitcher.text = 'Obecny dysk: '+drives[current_id]+'\nNastępny dysk'


    # Zapamiętanie ścieżki utworu wybranego w wysyłaniu utworu
    def file_selected(self, *args):
        try:
            self.to_send = args[1][0]
        except:
            self.to_send = ''
        print("Do wysłania wybrano: ", self.to_send)


    # Obsługa przycisku do wysłania nowego pliku muzyczneg w zakładce wysyłania pliku (wysyłanie oddzielnym wątku)
    def button_send_file(self):
        t1 = threading.Thread(target=send_file, args=(sock_command, sock_out_file, self.to_send))
        t1.start()
        self.to_send = ''


    # Tworzenie tabeli pokazującą kolejkę utworów
    def generate_queue(self):
        # usunięcie wcześniejszej tabeli
        self.ids.gridqueue.clear_widgets()
        self.ids.song_title.text = break_line(self.now_playing)
        
        if len(self.queue) > 0:
            for title in self.queue:
                
                # stworzenie rzędu do tabeli
                move = Button(size_hint_x=None, width=50, height=50, on_release=self.switch_row, background_normal="zasoby\\uparrow.png")  # text="Do góry", 
                song = Label(text = break_line(title))
                delete = Button(size_hint_x=None, width=50, height=50, on_release=self.delete_row, background_normal="zasoby\\bin.png")  # text="Usuń", 

                self.ids.gridqueue.add_widget(move)
                self.ids.gridqueue.add_widget(song)
                self.ids.gridqueue.add_widget(delete)
        
        self.ids.gridqueue.height = len(self.queue)*60 + 40


    # Metoda odpowiedzialna za przesunięcie utworu o jedno miejsce w górę w kolejce
    def switch_row(self, instance):
        row_index = self.ids.gridqueue.children.index(instance) // 3

        if(len(self.queue)-row_index-1):
            self.queue[len(self.queue)-row_index-2], self.queue[len(self.queue)-row_index-1] \
            = self.queue[len(self.queue)-row_index-1], self.queue[len(self.queue)-row_index-2]

            self.generate_queue()


    # Metoda odpowiedzialna za usunięcie utworu z kolejki
    def delete_row(self, instance):
        row_index = self.ids.gridqueue.children.index(instance) // 3

        self.ids.gridqueue.clear_widgets()
        self.queue.pop(len(self.queue)-row_index-1)

        self.generate_queue()


    # Obsługa przycisków do aktualizacji wyświetlanej kolejki/tytułu piosenki w tab1(RADIO) i tab2(KOLEJKA)
    def button_request_queue(self):
        t1 = threading.Thread(target=receive_queue, args=(sock_command, ))
        t1.start()


    # Obsługa przycisku do wysyłania zmodyfikowanej kolejki w tab2(KOLEJKA)
    def button_send_queue(self):
        t1 = threading.Thread(target=send_updated_queue, args=(sock_command, self.queue))
        t1.start()


    # Obsługa przycisku do pomijania piosenki w tab1(RADIO)
    def button_skip_song(self):
        t1 = threading.Thread(target=skip, args=(sock_command, ))
        t1.start()


    

class TabbedPanelApp(App):
    global sock_command
    def build(self):
        
        self.title = 'Radio FRJS FM'
        self.icon = 'zasoby\\logo.png'
        Window.minimum_height = 630
        Window.minimum_width = 800
        Window.size = (800, 630)
        Window.clearcolor = (0.14, 0.16, 0.18, 1)
        Window.bind(on_request_close=self.close_app)

        global application
        application = RadioGUI()
        return application
    
    def close_app(self, *args):
        sock_command.send(bytes("close_socks", "utf-8"))


#------------------------------------------------


if __name__ == '__main__':

    with open("config.txt") as file:
        HOST = file.readline()
        print("HOST: ", HOST)
        PORT = 1100
        print("PORT: ", PORT)

    # Utworzeie gniazd
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock_command, \
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock_in_audio, \
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock_out_file: 

        # Otwarcie połączeń
        sock_command.connect((HOST, PORT))
        time.sleep(0.1)
        sock_in_audio.connect((HOST, PORT))
        time.sleep(0.1)
        sock_out_file.connect((HOST, PORT))

        # Uruchomienie wątku odbierającego dźwięk od serwera
        t1 = threading.Thread(target=recieve_and_play, args=(sock_in_audio,))
        t1.start()

        # Uruchomienie okna aplikacji
        Builder.load_file('radio.kv')
        TabbedPanelApp().run()

        # Zamknięcie gniazd
        sock_out_file.close()
        sock_in_audio.close()
        sock_command.close()
