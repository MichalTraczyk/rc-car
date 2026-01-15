using UnityEngine;
using Unity.WebRTC;
using System.Collections;
using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using SocketIOClient;
using TMPro;
using UnityEngine.UI;

public class SessionController : MonoBehaviour
{
    [Header("UI Elements")]
    [SerializeField] private Button refreshButton;
    [SerializeField] private TMP_Dropdown carListDropdown;
    [SerializeField] private Button connectButton;
    [SerializeField] private Button disconnectButton;
    [SerializeField] private TextMeshProUGUI statusText;
    [SerializeField] private RawImage videoDisplay;
    [SerializeField] private AudioSource audioOutput;
    
    [Header("Settings")]
    [SerializeField] private string signalingServerUrl = "http://localhost:8080";
    
    private SocketIO socket;
    private RTCPeerConnection peerConnection;
    private List<CarInfo> availableCars = new List<CarInfo>();
    private string selectedRoomCode;
    private bool isConnected = false;
    
    private DelegateOnIceCandidate onIceCandidate;
    private DelegateOnIceConnectionChange onIceConnectionChange;
    private DelegateOnTrack onTrack;
    private RTCDataChannel dataChannel;
    private void Awake()
    {
        refreshButton.onClick.AddListener(RefreshCarList);
        connectButton.onClick.AddListener(ConnectToCar);
        disconnectButton.onClick.AddListener(DisconnectFromCar);
        
        // Initialize delegates
        onIceCandidate = candidate => OnIceCandidate(candidate);
        onIceConnectionChange = state => OnIceConnectionChange(state);
        onTrack = e => OnTrack(e);
        
        disconnectButton.interactable = false;
    }

    private void Start()
    {
        StartCoroutine(WebRTC.Update());
        InitializeSocket();
        UpdateStatus("Ready to connect");
    }
    private void Update()
    {
        if (isConnected && dataChannel != null && dataChannel.ReadyState == RTCDataChannelState.Open)
        {
            SendInput();
        }
    }
    private void SendInput()
    {
        float horizontal = Input.GetAxis("Horizontal");
        float vertical = Input.GetAxis("Vertical");
    
        // Create a simple JSON or string command
        var controlData = new {
            w = vertical,
            a = horizontal
        };
        string json = JsonConvert.SerializeObject(controlData);
        Debug.Log($"Sending: {json}");
        dataChannel.Send(json);
    }
    private async void InitializeSocket()
    {
        socket = new SocketIO(signalingServerUrl);
        
        socket.OnConnected += (sender, e) =>
        {
            Debug.Log("Socket.IO Connected!");
        };
        
        socket.OnDisconnected += (sender, e) =>
        {
            Debug.Log("Socket.IO Disconnected!");
        };
        
        socket.OnError += (sender, e) =>
        {
            Debug.LogError($"Socket.IO Error: {e}");
        };
        
        socket.On("car-list-updated", response =>
        {
            Debug.Log("Car list updated event received");
            UnityMainThreadDispatcher.Instance().Enqueue(() =>
            {
                RefreshCarList();
            });
        });
        
        socket.On("offer", response =>
        {
            Debug.Log("OFFER EVENT RECEIVED!");
            try 
            {
                // Get the raw string of the first argument in the response
                string rawJson = response.ToString(); 
        
                // Use Newtonsoft to parse the outer object
                var data = JArray.Parse(rawJson)[0];
        
                // Extract the offer string (which is a JSON string itself)
                string offerSdpJson = data["offer"].ToString();

                UnityMainThreadDispatcher.Instance().Enqueue(() =>
                {
                    StartCoroutine(HandleOffer(offerSdpJson));
                });
            }
            catch (Exception e)
            {
                Debug.LogError($"Error parsing offer: {e.Message}");
            }
        });
        
        socket.On("ice-candidate", response =>
        {
            try
            {
                var data = JArray.Parse(response.ToString())[0];
                var candidateJson = data["candidate"].ToString();
        
                UnityMainThreadDispatcher.Instance().Enqueue(() =>
                {
                    StartCoroutine(HandleIceCandidate(candidateJson));
                });
            }
            catch (Exception e)
            {
                Debug.LogError($"ICE Candidate Error: {e.Message}");
            }
        });

        await socket.ConnectAsync();
        UpdateStatus("Connected to signaling server");
        
        // Get initial car list
        RefreshCarList();
    }

    private async void RefreshCarList()
    {
        await socket.EmitAsync("get-car-list", (response) =>
        {
            try
            {
                var carListJson = response.ToString();
                Debug.Log($"Raw car list response: {carListJson}");
                
                // Parse the response on background thread
                var outerArray = JArray.Parse(carListJson);
                var tempCarList = new List<CarInfo>();
                
                // The actual car list is in the first element
                if (outerArray.Count > 0)
                {
                    var innerArray = outerArray[0] as JArray;
                    
                    if (innerArray != null)
                    {
                        foreach (var item in innerArray)
                        {
                            tempCarList.Add(new CarInfo
                            {
                                roomCode = item["roomCode"].ToString(),
                                socketId = item["socketId"].ToString()
                            });
                        }
                    }
                }
                
                Debug.Log($"Parsed {tempCarList.Count} cars");
                
                // Update UI on main thread
                UnityMainThreadDispatcher.Instance().Enqueue(() =>
                {
                    availableCars = tempCarList;
                    UpdateCarDropdown();
                });
            }
            catch (Exception ex)
            {
                Debug.LogError($"Error parsing car list: {ex.Message}");
            }
        });
    }

    private void UpdateCarDropdown()
    {
        carListDropdown.ClearOptions();
        
        if (availableCars.Count == 0)
        {
            carListDropdown.options.Add(new TMP_Dropdown.OptionData("No cars available"));
            carListDropdown.interactable = false;
            connectButton.interactable = false;
            UpdateStatus("No cars available");
        }
        else
        {
            var options = availableCars.Select(car => 
                new TMP_Dropdown.OptionData($"Car: {car.roomCode}")
            ).ToList();
            
            carListDropdown.AddOptions(options);
            carListDropdown.interactable = true;
            connectButton.interactable = true;
            UpdateStatus($"Found {availableCars.Count} car(s)");
        }
        
        // Force dropdown refresh
        carListDropdown.RefreshShownValue();
    }

    private async void ConnectToCar()
    {
        if (availableCars.Count == 0)
        {
            UpdateStatus("No cars available");
            return;
        }

        selectedRoomCode = availableCars[carListDropdown.value].roomCode;
        UpdateStatus($"Connecting to {selectedRoomCode}...");
        
        // Join the room
        await socket.EmitAsync("join-room", selectedRoomCode);
        
        // Initialize peer connection
        InitializePeerConnection();
        
        connectButton.interactable = false;
        disconnectButton.interactable = true;
        refreshButton.interactable = false;
        carListDropdown.interactable = false;
    }

    private void InitializePeerConnection()
    {
        if (peerConnection != null)
        {
            peerConnection.Dispose();
        }

        var configuration = new RTCConfiguration
        {
            iceServers = new[]
            {
                new RTCIceServer { urls = new[] { "stun:stun.l.google.com:19302" } },
                new RTCIceServer { urls = new[] { "stun:stun1.l.google.com:19302" } }
            }
        };

        peerConnection = new RTCPeerConnection(ref configuration);
        
        peerConnection.OnDataChannel = channel =>
        {
            dataChannel = channel;
            dataChannel.OnOpen = () => Debug.Log("Data Channel Opened!");
            dataChannel.OnClose = () => Debug.Log("Data Channel Closed!");
            dataChannel.OnMessage = bytes => {
                Debug.Log("Car says: " + System.Text.Encoding.UTF8.GetString(bytes));
            };
        };
        
        
        peerConnection.OnIceCandidate = onIceCandidate;
        peerConnection.OnIceConnectionChange = onIceConnectionChange;
        peerConnection.OnTrack = onTrack;

        Debug.Log("Peer connection initialized");
    }

    private IEnumerator HandleOffer(string offerJson)
    {
        Debug.Log($"Attempting to parse Offer: {offerJson}");
        var offerMsg = JsonUtility.FromJson<SessionDescriptionMessage>(offerJson);
        
        if (offerMsg == null || string.IsNullOrEmpty(offerMsg.sdp))
        {
            Debug.LogError("Failed to parse Offer JSON! SDP is null.");
            yield break;
        }
        
        var offer = new RTCSessionDescription
        {
            type = RTCSdpType.Offer,
            sdp = offerMsg.sdp
        };

        var setRemoteOp = peerConnection.SetRemoteDescription(ref offer);
        yield return setRemoteOp;

        if (setRemoteOp.IsError)
        {
            Debug.LogError($"Failed to set remote description: {setRemoteOp.Error.message}");
            yield break;
        }
        Debug.Log("Remote description set. Creating answer...");

        // Create answer
        var answerOp = peerConnection.CreateAnswer();
        yield return answerOp;

        if (answerOp.IsError)
        {
            Debug.LogError($"Failed to create answer: {answerOp.Error.message}");
            yield break;
        }

        var answer = answerOp.Desc;
        var setLocalOp = peerConnection.SetLocalDescription(ref answer);
        yield return setLocalOp;

        if (setLocalOp.IsError)
        {
            Debug.LogError($"Failed to set local description: {setLocalOp.Error.message}");
            yield break;
        }

        Debug.Log("Answer created and set as local description");

        // Send answer to car via signaling server
        var answerJson = JsonUtility.ToJson(new SessionDescriptionMessage
        {
            type = "answer",
            sdp = answer.sdp
        });

        socket.EmitAsync("answer", new { roomCode = selectedRoomCode, answer = answerJson });
        Debug.Log("Answer sent to signaling server");
    }

    private IEnumerator HandleIceCandidate(string candidateJson)
    {
        var candidateMsg = JsonUtility.FromJson<IceCandidateMessage>(candidateJson);
        
        var candidate = new RTCIceCandidateInit
        {
            candidate = candidateMsg.candidate,
            sdpMid = candidateMsg.sdpMid,
            sdpMLineIndex = candidateMsg.sdpMLineIndex
        };

        var iceCandidate = new RTCIceCandidate(candidate);
        peerConnection.AddIceCandidate(iceCandidate);
        
        yield return null;
    }

    private async void OnIceCandidate(RTCIceCandidate candidate)
    {
        if (candidate == null || string.IsNullOrEmpty(candidate.Candidate))
            return;

        Debug.Log($"ICE Candidate: {candidate.Candidate}");
        
        var candidateJson = JsonUtility.ToJson(new IceCandidateMessage
        {
            candidate = candidate.Candidate,
            sdpMid = candidate.SdpMid,
            sdpMLineIndex = candidate.SdpMLineIndex ?? 0
        });

        await socket.EmitAsync("ice-candidate", new { roomCode = selectedRoomCode, candidate = candidateJson });
    }

    private void OnIceConnectionChange(RTCIceConnectionState state)
    {
        Debug.Log($"ICE Connection State: {state}");
        
        switch (state)
        {
            case RTCIceConnectionState.Connected:
                UpdateStatus("Connected to car!");
                isConnected = true;
                break;
            case RTCIceConnectionState.Disconnected:
                UpdateStatus("Disconnected from car");
                isConnected = false;
                break;
            case RTCIceConnectionState.Failed:
                UpdateStatus("Connection failed");
                isConnected = false;
                break;
            case RTCIceConnectionState.Closed:
                UpdateStatus("Connection closed");
                isConnected = false;
                break;
        }
    }

    private void OnTrack(RTCTrackEvent e)
    {
        Debug.Log($"Received track: {e.Track.Kind}");
        
        if (e.Track is VideoStreamTrack videoTrack)
        {
            videoTrack.OnVideoReceived += tex =>
            {
                if (videoDisplay != null)
                {
                    videoDisplay.texture = tex;
                }
            };
            UpdateStatus("Video stream received");
        }
        
        if (e.Track is AudioStreamTrack audioTrack)
        {
            if (audioOutput != null)
            {
                audioOutput.SetTrack(audioTrack);
                audioOutput.loop = true;
                audioOutput.Play();
            }
            UpdateStatus("Audio stream received");
        }
    }

    private async void DisconnectFromCar()
    {
        if (peerConnection != null)
        {
            peerConnection.Dispose();
            peerConnection = null;
        }

        if (videoDisplay != null)
        {
            videoDisplay.texture = null;
        }

        if (audioOutput != null)
        {
            audioOutput.Stop();
        }

        isConnected = false;
        connectButton.interactable = true;
        disconnectButton.interactable = false;
        refreshButton.interactable = true;
        carListDropdown.interactable = true;
        
        UpdateStatus("Disconnected");
        RefreshCarList();
    }

    private void UpdateStatus(string message)
    {
        if (statusText != null)
        {
            statusText.text = message;
        }
        Debug.Log($"Status: {message}");
    }

    private async void OnDestroy()
    {
        if (isConnected)
        {
            DisconnectFromCar();
        }

        if (socket != null)
        {
            await socket.DisconnectAsync();
            socket.Dispose();
            socket = null;
        }
    }

    [Serializable]
    private class SessionDescriptionMessage
    {
        public string type;
        public string sdp;
    }

    [Serializable]
    private class IceCandidateMessage
    {
        public string candidate;
        public string sdpMid;
        public int sdpMLineIndex;
    }

    [Serializable]
    private class CarInfo
    {
        public string roomCode;
        public string socketId;
    }
}