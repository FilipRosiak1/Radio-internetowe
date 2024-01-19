#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <string.h>
#include <arpa/inet.h>
#include <fcntl.h> // for open
#include <unistd.h> // for close
#include <pthread.h>
#include <iostream>
#include <vector>
#include <fstream>
#include <sstream>


#define AUDIOBUFFSIZE 10000
#define INBUFFSIZE 5000
#define COMMANDBUFFSIZE 100

using namespace std;

// struktura przechowująca gniazda użytokowników 
struct sock {
  int in_file;
  int out_sound;
  int command;
};

// wektor utworów
vector<string> song_queue;
// wektor użytkowników
vector<sock> users;

int users_counter = 0;

// funkcja sprawdzająca czy pierwszy element z wektora powtarza się gdzieś dalej


// funkcja odpowiedzialna za odebranie pliku od użytkownika
void * get_file(void *arg) {
  char title_buff[INBUFFSIZE];
  char data_buff[INBUFFSIZE];
  memset(&data_buff, 0, sizeof (data_buff));
  memset(&title_buff, 0, sizeof (title_buff));


  cout << "Rozpoczęto odbiór pliku" << endl;
  int newSocket = *((int *)arg);
  int n;

  n = recv(newSocket , title_buff , INBUFFSIZE , 0);

  ofstream song_file(title_buff, ios::binary);

  // odbieranie pliku
  while(1) {
    n = recv(newSocket , data_buff , INBUFFSIZE , 0);
    if(!strcmp(data_buff, "end_of_upload")) {
      break;
    }

    // jeśli użytkownik rozłączy się w trakcie to plik należy usunąć
    if(n == 0) {
      song_file.close();
      remove(title_buff);
      pthread_exit(NULL);
      cout << "Odebranie pliku nie powiodło się" << endl;
    }
    if(n > 0) {
      song_file.write(data_buff, n);
      memset(&data_buff, 0, sizeof (data_buff));
      
    }
  }
  // zapisanie i dodanie utworu do kolejki
  song_file.close();
  song_queue.push_back(title_buff);
  cout << "Otrzymano plik " << song_queue.back() << endl;


  pthread_exit(NULL);
}

// Funckja odpowiedzialna za przesłanie kolejki użytkownikowi
void action_send_queue(int user) {
  for(string title: song_queue) {
    cout << title << endl;
    send(users[user].command, title.c_str(), title.size(),0);
    send(users[user].command, " | ", 3,0);
  }
}

// Funkcja zamykająca gniazda użytkownika
void action_close_user_socks(int user) {
  close(users[user].in_file);
  close(users[user].command);
  close(users[user].out_sound);
  users.erase(users.begin() + user);
}

// Funkcja odbierająca nową kolejkę od użytkownika i podmieniająca starą kolejkę
void action_update_queue(int user) {
  char new_queue[INBUFFSIZE];
  memset(&new_queue, 0, sizeof(new_queue));
  int n = recv(users[user].command, new_queue, INBUFFSIZE, 0);

  vector<string> result;
  string token;
  istringstream iss(new_queue);
  while (getline(iss, token, '|')) {
    size_t start = token.find_first_not_of(" \t\n\r");
    size_t end = token.find_last_not_of(" \t\n\r");

    if (start != string::npos && end != string::npos)
        result.push_back(token.substr(start, end - start + 1));
  }

  // usunięcie starej kolejki i dodanie nowej
  song_queue.erase(song_queue.begin() + 1, song_queue.end());
  song_queue.insert(song_queue.end(), result.begin(), result.end());

  cout << "Nowa kolejka:" << endl;
  for (string x: song_queue) {
    cout << x << endl;
  }
  cout << "Zaktualizowano kolejkę" << endl;
}

// Główny wątek, odpowiedzialny za przesyłanie dzwięku i obsługę poleceń od użytkowników
void * radio(void *) {
  int skip = 0;
  int n;
  char audio_buff[AUDIOBUFFSIZE];
  char command_buff[COMMANDBUFFSIZE];
  
  cout << "Rozpoczęto nadawanie" << endl;

  while(1) {
    // oczekiwanie na użytkowników 
    if(users.size()==0){
      sleep(2);
    }
    // jeśli nie ma innych utworów, dodać utwór z listy podstawowych
    if(song_queue.empty()) {
      song_queue.push_back("rr");
    }


    while(!song_queue.empty() && users.size()>0) {
      cout << "Rozpoczęto odtwarzanie: " << song_queue[0].c_str() << endl;
      ifstream file(song_queue[0], ios::binary);
      memset(&audio_buff, 0, sizeof(audio_buff));

      while(!file.eof()) {
        file.read(audio_buff, AUDIOBUFFSIZE);

        for(auto user_num = 0; user_num < users.size(); user_num++) {
          // wysłanie dźwięku do użytkownika          
          send(users[user_num].out_sound, audio_buff, AUDIOBUFFSIZE, 0);
          memset(&command_buff, 0, sizeof(command_buff));

          // obsługa poleceń od użytkownika
          n = recv(users[user_num].command, command_buff, COMMANDBUFFSIZE, MSG_DONTWAIT);

          if(n == 0) {
            action_close_user_socks(user_num);
            user_num--;
          }

          if(n > 0) {
            cout << "Otrzymano polecenie od użytkownika " << user_num << ":" << command_buff << endl;
            if(!strcmp(command_buff, "close_socks")) {
              action_close_user_socks(user_num);
              user_num--;
            }
            if(!strcmp(command_buff, "queue_req")) {
              action_send_queue(user_num);
            }

            if(!strcmp(command_buff, "queue_upd")) {
              action_update_queue(user_num);
            }

            if(!strcmp(command_buff, "skip_song")) {
              skip = 1;
              break;
            }

            if(!strcmp(command_buff, "sending_song")) {
              pthread_t download_thread_id;
              if( pthread_create(&download_thread_id, NULL, get_file, &users[user_num].in_file) != 0 )
		   		      cout << "Nie udalo sie stworzyc watku odbierajacego plik" << endl;
              else 
                pthread_detach(download_thread_id);         
            }
          }
        }
        // jeśli flaga odpowiedzialna za pominięcie to przerywamy pętlę wysyłania utworu
        if(skip) {
          skip = 0;
        break;
        }
     } 
      
      file.close();
      // jeżeli odtwarzany jest utwór inny niż podstawowy utwór, to po zagraniu utwór zostaje usunięty z serwera
      int to_remove = 1;
      if(strcmp(song_queue[0].c_str(), "rr") && (song_queue.size() > 1)) {
        for(int i = 1; i < song_queue.size(); i++) {
          if(song_queue[0] == song_queue[i]) {
            to_remove = 0;
          }
        }
        if(to_remove) {
          cout << "Usuwam utwór: " << song_queue[0] << endl;
          remove(song_queue[0].c_str());
        }
      }

      song_queue.erase(song_queue.begin());

    }
  }
  cout << "Wyłączanie radia" << endl;
  pthread_exit(NULL);
}



int main(){
  int serverSocket;
  struct sockaddr_in serverAddr;
  struct sockaddr_storage serverStorage;
  socklen_t addr_size;
  struct sock sockets;
  pthread_t radio_thread_id;

  serverSocket = socket(PF_INET, SOCK_STREAM, 0);

  serverAddr.sin_family = AF_INET;

  serverAddr.sin_port = htons(1100);

  serverAddr.sin_addr.s_addr = htonl(INADDR_ANY);

  memset(serverAddr.sin_zero, '\0', sizeof serverAddr.sin_zero);

  bind(serverSocket, (struct sockaddr *) &serverAddr, sizeof(serverAddr));

  if(listen(serverSocket,50)==0)
    printf("Listening\n");
  else {
    printf("Error listen\n");
  }

  if( pthread_create(&radio_thread_id, NULL, radio, 0) != 0 )
    cout << "Nie udało się stworzyć wątku radia" << endl;
  else 
    pthread_detach(radio_thread_id);
    

  while(1) {
    // przyjmowanie połączeń przychodzących
    addr_size = sizeof serverStorage;
    sockets.command = accept(serverSocket, (struct sockaddr *) &serverStorage, &addr_size);
    sockets.out_sound = accept(serverSocket, (struct sockaddr *) &serverStorage, &addr_size);
    sockets.in_file = accept(serverSocket, (struct sockaddr *) &serverStorage, &addr_size);

    users.push_back(sockets);
      
  }
  cout << "Mam nadzieję że to się nie wypisze" << endl;
  
  return 0;
}