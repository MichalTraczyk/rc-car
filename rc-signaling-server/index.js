const express = require('express');
const http = require('http');
const { Server } = require("socket.io");

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
    cors: { origin: "*" }
});

// Store active cars: { socketId: { roomCode: "1234", socketId: "abc" } }
let activeCars = {};
// Store rooms with their members
let rooms = {};

io.on('connection', (socket) => {
    console.log(`Connected: ${socket.id}`);

    // Car registers itself with a room code
    socket.on('register-car', (roomCode) => {
        socket.join(roomCode);
        activeCars[socket.id] = {
            roomCode,
            role: 'car',
            socketId: socket.id
        };

        // Initialize room if needed
        if (!rooms[roomCode]) {
            rooms[roomCode] = { car: null, controllers: [] };
        }
        rooms[roomCode].car = socket.id;

        console.log(`Car registered in room: ${roomCode} with ID: ${socket.id}`);

        // Broadcast updated car list to all clients
        io.emit('car-list-updated', getCarList());
    });

    // Controller requests list of available cars
    socket.on('get-car-list', (callback) => {
        const list = getCarList();
        console.log(`Sending car list: ${JSON.stringify(list)}`);
        callback(list);
    });

    // Controller joins a room to connect to a car
    socket.on('join-room', (roomCode) => {
        socket.join(roomCode);
        console.log(`Controller ${socket.id} joined room: ${roomCode}`);

        // Track controller in room
        if (rooms[roomCode]) {
            rooms[roomCode].controllers.push(socket.id);
        }

        // Notify the car that a controller has joined
        socket.to(roomCode).emit('controller-joined', { controllerId: socket.id });
        console.log(`Notified car in room ${roomCode} about controller ${socket.id}`);
    });

    // Forward WebRTC signaling messages (offer, answer, ice candidates)
    socket.on('offer', (data) => {
        console.log(`Received offer from ${socket.id} for room: ${data.roomCode}`);
        console.log(`Offer data: ${data.offer.substring(0, 100)}...`);
        socket.to(data.roomCode).emit('offer', {
            senderId: socket.id,
            offer: data.offer
        });
        console.log(`Forwarded offer to room: ${data.roomCode}`);
    });

    socket.on('answer', (data) => {
        console.log(`Received answer from ${socket.id} for room: ${data.roomCode}`);
        console.log(`Answer data: ${data.answer.substring(0, 100)}...`);
        socket.to(data.roomCode).emit('answer', {
            senderId: socket.id,
            answer: data.answer
        });
        console.log(`Forwarded answer to room: ${data.roomCode}`);
    });

    socket.on('ice-candidate', (data) => {
        console.log(`Received ICE candidate from ${socket.id} for room: ${data.roomCode}`);
        socket.to(data.roomCode).emit('ice-candidate', {
            senderId: socket.id,
            candidate: data.candidate
        });
        console.log(`Forwarded ICE candidate to room: ${data.roomCode}`);
    });

    socket.on('disconnect', () => {
        if (activeCars[socket.id]) {
            const roomCode = activeCars[socket.id].roomCode;
            console.log(`Car ${roomCode} disconnected`);
            delete activeCars[socket.id];

            // Clean up room
            if (rooms[roomCode]) {
                delete rooms[roomCode];
            }

            // Notify all clients that car list has changed
            io.emit('car-list-updated', getCarList());
        } else {
            // Controller disconnected - remove from rooms
            for (let roomCode in rooms) {
                const idx = rooms[roomCode].controllers.indexOf(socket.id);
                if (idx > -1) {
                    rooms[roomCode].controllers.splice(idx, 1);
                    console.log(`Controller ${socket.id} removed from room ${roomCode}`);
                }
            }
        }
        console.log(`Disconnected: ${socket.id}`);
    });
});

function getCarList() {
    return Object.values(activeCars).map(car => ({
        roomCode: car.roomCode,
        socketId: car.socketId
    }));
}

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => console.log(`Signaling server running on port ${PORT}`));