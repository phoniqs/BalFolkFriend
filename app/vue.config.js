const WorkerPlugin = require("worker-plugin");
const path = require('path');
const fs = require('fs')
const packageJson = fs.readFileSync('./package.json')
const version = JSON.parse(packageJson).version || "";
const webpack = require('webpack');

module.exports = {
    transpileDependencies: [
        'vuetify'
    ],
    configureWebpack: {
        plugins: [
            new WorkerPlugin({ chunkFilename: '[id].worker-chunk.js' }),
new webpack.NormalModuleReplacementPlugin(
                /(^|!)midi\//,
                path.resolve(__dirname, 'stubs/midi/index.js')
            ),
            // This is just to pull the version from package.json into ffConfig.js
            new webpack.DefinePlugin({
                'process.env': {
                    PACKAGE_VERSION: '"' + version + '"'
                }
            })
        ],
    },
    chainWebpack: config => {
        
        // Getting PWA stuff like this to work with vue / webpack is a faff.
        //  It's super easy to just supply the manifest file in /public ourselves.
        config.plugins.delete("pwa");

           },
    pwa: {
        name: "FolkFriend",
        theme_color: '#055581',
        background_color: '#055581',
    }
}
