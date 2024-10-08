# radiotelegram

Record Baofeng voice transmissions with RTL-SDR and send them as Telegram voice messages automatically

## how to

### dependencies
1. connect rtl-sdr ([arch wiki](https://wiki.archlinux.org/title/RTL-SDR))
2. install [GQRX](https://www.gqrx.dk/) via package manager
3. install project deps with `pipenv install`

### sdr
1. run gqrx, tune to your radio frequency 
2. select Narrow FM modulation for Baofeng radios
3. press A to set squelch automatically

now press TX button on your radio, say something, check the sound quality, tune other settings (audio gain, agc?) as needed. you should clearly hear yourself, but ZERO sound should be played when you are NOT transmitting, it's essential for the script to work. adjust the squelch.

### rx.py
1. copy `example.env` to `.env`, edit the file to fill telegram token and chat id. then:
2.  run the script:
    ```
    pipenv shell
    source .env
    python3 ./rx.py
    ```
3. - open `pavucontrol` or similar audio mixer
    - go to recording tab
    - change rx.py recording device to "MONITOR of system audio", so that the script listens to the output, not the microphone.
4. now voice messages will be forwarded to telegram chat. enjoy.

## license
MIT
