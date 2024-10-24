const socket = io.connect('http://' + document.domain + ':' + location.port);

const room = document.querySelector('#room').innerText; // Get room name from somewhere
const username = document.querySelector('#username').innerText; // Get username from somewhere

document.querySelector('#message-form').onsubmit = function(e) {
    e.preventDefault();
    const messageInput = document.querySelector('#message-input');
    const message = messageInput.value;
    messageInput.value = '';

    socket.emit('message', {message: message, room: room, username: username});
};

socket.on('message', function(msg) {
    const messagesDiv = document.querySelector('#messages');
    messagesDiv.innerHTML += '<div class="chat-message"><span>' + msg + '</span></div>';
});
