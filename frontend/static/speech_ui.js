const SPEECH_SERVER = 'http://localhost:5100';

async function speakTextFromUI(text, profile=null){
    if(!text) return;
    try{
        const res = await fetch(`${SPEECH_SERVER}/api/speak`,{
            method:'POST',headers:{'Content-Type':'application/json'},
            body: JSON.stringify({text:text, profile:profile})
        });
        const data = await res.json();
        console.log('speak response', data);
    }catch(e){
        console.error('Speak error', e);
        alert('Speak failed: '+e.message);
    }
}

async function listenOnceFromUI(){
    try{
        const res = await fetch(`${SPEECH_SERVER}/api/listen`);
        const data = await res.json();
        if(data.success){
            // Insert recognized text into command input if exists
            const input = document.getElementById('commandInput');
            if(input) input.value = data.text;
            addMessageToChat('You', `🎙 ${data.text}`, 'user-message');
        } else {
            alert('Listen failed: ' + (data.error||data.message));
        }
    }catch(e){
        console.error('Listen error', e);
        alert('Listen failed: '+e.message);
    }
}
