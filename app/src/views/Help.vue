<template>
    <v-container>
        <v-card class="pa-5 my-2">
            <h1>About</h1>
            <p>
                BalFolkFriend listens to instrumental folk music, transcribes the
                melody to sheet music, and searches a database of traditional
                tunes for matches. You may either use the microphone on your
                device, or upload an existing audio file. BalFolkFriend runs
                entirely in browser and works without an internet connection.
            </p>
        </v-card>
        <v-card
            ref="helpDownload"
            class="pa-5 my-2"
        >
            <h1>Download</h1>
            <p>
                BalFolkFriend is a "Web App", which means it installs onto your
                Home Screen just like any other app.
            </p>
            <p
                v-if="isPWA"
                align="center"
            >
                BalFolkFriend is installed <v-icon class="pb-1 Installed">
                    {{ icons.checkCircle }}
                </v-icon>
            </p>
            <p v-else-if="ua.isSafari && ua.isMobile">
                On iOS Safari,
                <ul>
                    <li>
                        Tap <v-icon class="pb-2">
                            {{ icons.iosShare }}
                        </v-icon> "share"
                    </li>
                    <li>Scroll down</li>
                    <li>
                        Tap <v-icon class="pb-1">
                            {{ icons.iosAddToHomeScreen }}
                        </v-icon> "add to home screen"
                    </li>
                </ul>
            </p>
            <p v-else-if="ua.isChrome && ua.isMobile">
                On Chrome mobile,
                <ul>
                    <li>
                        Tap <v-icon class="pb-1">
                            {{ icons.dotsVertical }}
                        </v-icon> "Customise"
                    </li>
                    <li>
                        Tap <v-icon class="pb-1">
                            {{ icons.cellphoneArrowDown }}
                        </v-icon> "Install BalFolkFriend"
                    </li>
                </ul>
            </p>
            <p v-else-if="ua.isChrome && !ua.isMobile">
                On Chrome desktop,
                <ul>
                    <li>
                        Tap <v-icon class="pb-1">
                            {{ icons.cellphoneArrowDown }}
                        </v-icon> "install app"
                    </li>
                </ul>
            </p>
            <p v-else>
                To install BalFolkFriend, navigate to the settings of your browser
                and select "Add to Home Screen" or "Install App".
            </p>
        </v-card>
        <v-card
            ref="helpShare"
            class="pa-5 my-2"
        >
            <h1>Share</h1>
            <p>Scan the QR code on another device to open BalFolkFriend.</p>
            <v-img
                src="@/assets/qr-code.svg"
                class="mx-auto QRCode"
                align-center
                center
                contain
            />
        </v-card>
        <v-card class="pa-5 my-2">
            <h1>Feedback</h1>
            <p>
                BalFolkFriend is a fork of FolkFriend, maintained independently. Please
                send bug reports, feature requests, or general feedback about
                this version to <a
                    class="feedbackEmail"
                    href="mailto:arpagandekniga@gmail.com"
                >arpagandekniga@gmail.com</a>.
                Please do not contact the original author about problems with
                this version.
            </p>
        </v-card>
        <v-card class="pa-5 my-2">
            <h1>Credits &amp; licence</h1>
            <p>
                BalFolkFriend is a <strong>modified version</strong> of
                <a
                    href="https://folkfriend.app"
                    target="_blank"
                    rel="noopener"
                >FolkFriend</a> by Tom Wyllie
                (<a
                    href="https://github.com/TomWyllie/folkfriend"
                    target="_blank"
                    rel="noopener"
                >source code</a>), released under the
                <a
                    href="https://www.gnu.org/licenses/gpl-3.0.html"
                    target="_blank"
                    rel="noopener"
                >GNU General Public License v3</a>.
                The recognition engine and app are his work; this version only
                replaces the tune index and adapts the branding and some
                screens.
            </p>
            <p>
                The tune index is built from the <a href="https://baloche.onth.org" target="_blank" rel="noopener">Baloche</a> directory of traditional / balfolk scores; each tune links back to its Baloche page. Scores were converted automatically and may contain errors.
            </p>
            <p>
                The source code of this modified version is available at
                <a
                    href="https://github.com/phoniqs/BalFolkFriend"
                    target="_blank"
                    rel="noopener"
                >github.com/phoniqs/BalFolkFriend</a>.
            </p>
            <p>
                If you enjoy this app, please consider
                <a
                    href="https://donorbox.org/help-support-development-of-folkfriend"
                    target="_blank"
                    rel="noopener"
                >supporting the original FolkFriend developer</a>.
            </p>
        </v-card>
        <p class="AppInfo">
            App version: {{ frontendVersion }}<br>Backend version:
            {{ backendVersion }}<br>FolkFriend © {{ currentYear }} Tom Wyllie · modified version · GPLv3
        </p>
    </v-container>
</template>

<script>
import store from '@/services/store.js';
import ffConfig from '@/ffConfig.js';
import eventBus from '@/eventBus';
import utils from '@/js/utils.js';

import {
    mdiCellphoneArrowDown,
    mdiCheckCircleOutline,
    mdiDotsVertical,
    mdiExportVariant,
    mdiPlusBoxOutline,
} from '@mdi/js';

export default {
    name: 'HelpView',
    props: {
        'download': {
            type: Boolean,
            required: false,
            default: false
        }, 
        'share':  {
            type: Boolean,
            required: false,
            default: false
        }, 
    },
    data: () => ({
        icons: {
            iosShare: mdiExportVariant,
            iosAddToHomeScreen: mdiPlusBoxOutline,
            checkCircle: mdiCheckCircleOutline,
            // TODO these haven't been added yet
            // mdiInstallDesktop: mdiInstallDesktop,
            // mdiInstallMobile: mdiInstallMobile,
            cellphoneArrowDown: mdiCellphoneArrowDown,
            dotsVertical: mdiDotsVertical,
        },
        currentYear: new Date().getFullYear(),
        isPWA: utils.checkStandalone(),
    }),
    computed: {
        backendVersion() {
            return store.state.backendVersion;
        },
        frontendVersion() {
            return ffConfig.FRONTEND_VERSION;
        },
    },
    created: function () {
        eventBus.$emit('parentViewActivated');
        this.ua = utils.checkUserAgent();
    },
    mounted: function () {
        if(this.download) {
            this.$refs['helpDownload'].$el.scrollIntoView();
        } else if(this.share) {
            this.$refs['helpShare'].$el.scrollIntoView();
        }
    },
};
</script>

<style scoped>
.feedbackEmail {
    font-weight: bold;
    color: --var(--v-primary-base);
}

.v-card {
    scroll-margin-top: 60px;
}

.AppInfo {
    color: dimgray;
    text-align: center;
    font-size: smaller;
}

.Installed {
    color: var(--v-secondary-base);
}

.QRCode {
    max-width: 240px;
    min-width: 100px;
    width: 40vw;
    fill: var(--v-primary-darken1);
}

</style>