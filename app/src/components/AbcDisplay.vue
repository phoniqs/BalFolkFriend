<template>
    <v-card elevation="0">
        <v-container
            v-if="showAbcText"
            class="ma-0 pa-0"
        >
            <span class="abcTextView mx-auto">{{ abcText }}</span>
        </v-container>
        <div
            :class="{ FullScreenAbcDisplay: fullscreen }"
            class="abcSheetMusic"
            @click="exitFullScreen"
        >
            <!-- Render ABC sheet music here -->
            <div ref="svgDiv" />
        </div>
        <v-row
            wrap
            justify="center"
            class="py-2"
        >
            <v-btn
                class="mx-1 px-3 abcControls"
                @click="restartPlaying"
            >
                <v-icon>{{ icons.replay }}</v-icon>
            </v-btn>
            <v-btn
                :loading="loading"
                class="mx-1 px-3 abcControls"
                @click="startPlaying"
            >
                <v-icon v-if="paused">
                    {{ icons.play }}
                </v-icon>
                <v-icon v-else>
                    {{ icons.pause }}
                </v-icon>
            </v-btn>
            <v-btn
                class="mx-1 px-3 abcControls"
                @click="stopPlaying"
            >
                <v-icon>{{ icons.stop }}</v-icon>
            </v-btn>
            <v-btn
                class="mx-1 px-3 abcControls"
                @click="goFullScreen"
            >
                <v-icon>{{ icons.fullscreen }}</v-icon>
            </v-btn>
        </v-row>
    </v-card>
</template>

<script>
import { mdiFullscreen, mdiPause, mdiPlay, mdiReplay, mdiStop } from '@mdi/js';
import store from '@/services/store.js';
import abcjs from 'abcjs';
import { getAudioContext, setActiveSynth, releaseSynth } from '@/services/player.js';

export default {
    name: 'AbcDisplay',
    props: {
        abc: {
            type: String,
            required: true,
        },
        mode: {
            type: String,
            required: false,
            default: null
        },
        meter: {
            type: String,
            required: false,
            default: null
        },
    },
    data: function () {
        return {
            paused: true,
            started: false,
            loading: false,
            fullscreen: false,

            icons: {
                fullscreen: mdiFullscreen,
                pause: mdiPause,
                play: mdiPlay,
                replay: mdiReplay,
                stop: mdiStop,
            },
        };
    },
    computed: {
        abcText: function () {
            const abcLines = [];
	abcLines.push('X:1');
            if (this.mode) {
                abcLines.push(`K:${this.mode}`);
            }
            if (this.meter) {
                abcLines.push(`M:${this.meter}`);
            }
            abcLines.push(this.abc);
            return abcLines.join('\n');
        },
        showAbcText: function () {
            return store.userSettings.showAbcText;
        },
    },
    created: function () {
        // Volontairement non réactifs
        this.synth = null;
        this.visualObj = null;
    },
    mounted: function () {
	        this.visualObj = abcjs.renderAbc(
            this.$refs.svgDiv,
            this.abcText,
            { responsive: 'resize' }
        )[0];
    },
    beforeDestroy: function () {
        this.discardSynth();
    },
    methods: {
        discardSynth: function () {
            if (this.synth) {
                const synth = this.synth;
                this.synth = null;
                releaseSynth(synth);
                try { synth.stop(); } catch (e) { console.debug(e); }
            }
            this.started = false;
            this.paused = true;
        },
        play: async function () {
            if (this.loading) return;
            this.loading = true;
            try {
                // À faire tout de suite : le navigateur exige un geste de l'utilisateur
                const audioContext = getAudioContext();
                if (audioContext.state === 'suspended') {
                    await audioContext.resume();
                }

                const synth = new abcjs.synth.CreateSynth();
                await synth.init({
                    visualObj: this.visualObj,
                    audioContext: audioContext,
                });
                await synth.prime();

                setActiveSynth(synth, () => {
                    this.synth = null;
                    this.started = false;
                    this.paused = true;
                });
                this.synth = synth;
                synth.start();
                this.started = true;
                this.paused = false;
            } finally {
                this.loading = false;
            }
        },
        startPlaying: async function () {
            try {
                if (this.synth && !this.paused) {
                    this.synth.pause();
                    this.paused = true;
                } else if (this.synth && this.started) {
                    this.synth.resume();
                    this.paused = false;
                } else {
                    await this.play();
                }
            } catch (err) {
                console.error('Playback failed', err);
                this.discardSynth();
            }
        },
        stopPlaying: function () {
            this.discardSynth();
        },
        restartPlaying: async function () {
            this.discardSynth();
            try {
                await this.play();
            } catch (err) {
                console.error('Playback failed', err);
                this.discardSynth();
            }
        },
        goFullScreen: function () {
            this.$emit('abcGoFullScreen');
            this.fullscreen = true;
        },
        exitFullScreen: function () {
            this.$emit('abcExitFullScreen');
            this.fullscreen = false;
        },
    },
};
</script>

<style scoped>
.abcTextView {
    font-family: Courier, serif;
    white-space: pre-wrap;
    display: inline-block;
}

.FullScreenAbcDisplay {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: white;
    overflow-y: scroll;

    /* TODO z index flicker here isn't great */
    z-index: 10;
}

.FullScreenAbcDisplay > div {
    min-height: 100%;
}

.abcControls {
    min-width: 0 !important;
}
</style>