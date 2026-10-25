# @futuremagic/audio

Game sound on Web Audio, and the script that makes a game's sounds and music through OpenRouter.

```ts
import { AudioEngine } from '@futuremagic/audio/web';
import { MusicPicker, Stride, strideAt } from '@futuremagic/audio';

const sound = new AudioEngine({ base: `${import.meta.env.BASE_URL}sound/`, seed });  // opens on the first press
sound.setVolume('master', 0.8);

// every frame:
sound.listen([eye.x, eye.y, eye.z], [look.x, look.y, look.z]);
sound.bed('bed/wind-open', 0.5);                                   // ambience: set each tick it should be heard
sound.bed('bed/falls', 0.9, { at: [fx, fy, fz], ref: 30 }, 'fall'); // placed: heard from the waterfall
sound.settle();                                                    // beds not set this tick fade out
if (stride.step(speed, dt, strideAt(speed))) sound.play('step/grass', { gain: 0.5 });
sound.update();

// music: a picker per mood, the engine crossfades
const picker = new MusicPicker({ day: ['music/day-1', 'music/day-2'], fight: ['music/fight-1'] }, seed, { urgent: ['fight'] });
const next = picker.want(mood, seconds);
if (next !== undefined) sound.music(next, 4);
sound.onMusicEnded = () => picker.ended(seconds);
sound.duck(0.4);                 // a dialog is open
sound.muffle(500);               // under water
sound.echo(1.2, 0.3);            // a stone hall
```

| | What |
| --- | --- |
| `.` (pure) | `SoundIndex` (what `tools/make.mjs` writes), `pickTake` (seeded take, pitch and gain, never the same take twice running), `Stride` and `strideAt` (footsteps, hooves, strokes by distance), `MusicPicker` (moods with several pieces: held a while, urgent moods cut in, rests, no repeats), `roomImpulse` (a room's echo from its T60). |
| `./web` | `AudioEngine`: buses `world` (muffled, echoed), `body`, `ui`, `music`; beds as two crossfading chains (or one through an HRTF panner when placed); seeded one-shots in the head or from a place; two music decks (media elements, streamed) that crossfade; ducking; decoded takes kept under a budget (least recently heard go first). |
| `tools/make.mjs` | The game's `sounds.json` (prompts, kinds, takes reused from other games with `from`) into its sound folder and `index.json`: Seed Audio for sounds, Lyria for music, models resolved at run time by Arnd's preferences; takes cut (steps out of a walking take), levelled and encoded (32 kHz mono effects, 44.1 kHz music). Needs `OPEN_ROUTER_KEY` and ffmpeg; never part of CI. |

Came from Solarpolis (`src/audio/sound.ts`, `scripts/sound/make.mjs`). First used by MasterWorld.
