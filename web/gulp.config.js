/* eslint-env node */
/* eslint strict: 0 */

module.exports = function () {
    var client = './';
    var clientApp = client + 'app/';
    var report = './report/';
    var specRunnerFile = 'specs.html';
    var temp = './.tmp/';
    var languages = ['en', 'fr'];
    var nodeModules = 'node_modules';
    var packages = {
        json: require('./package.json'),
        directory: './node_modules',
        ignorePath: '../..'
    };
    var config = {
        // all javascript that we want to vet
        alljs: [
            './app/**/*.js',
            './js/**/*.js',
            './*.js'
        ],
        build: '../static/',
        client: client,
        clientApp: clientApp,
        languages: languages,

        index: 'index.html',
        js: [
            'app/**/*.module.js',
            'app/**/*.service.js',
            'app/**/*.directive.js',
            'app/**/*.js',
            'js/*.js',
            '!app/**/*.spec.js'
        ],
        html: [
            client + 'html/**/*.html',
            clientApp + '**/*.html'
        ],
        images: [
            'img/**/*'
        ],
        gulpSassOptions: {
            includePaths: [
                'css/cm',
                'node_modules/bootstrap-sass/assets/stylesheets',
                'node_modules/bootstrap-material-design/sass'
            ]
        },
        scss_compile: [
            'css/cm.scss'
        ],
        scss: [
            'css/**/*.scss'
        ],
        css: 'cm.css',
        fonts: [
            'node_modules/bootstrap-sass/assets/fonts/**/*',
            'node_modules/font-awesome/fonts/*.*',
            'fonts/**/*.*'
        ],
        locales: {}, // initialize just after
        /**
         * optimized files
         */
        optimized: {
            app: 'cm.js',
            lib: 'vendor.js'
        },

        /**
         * plato
         */
        plato: {js: clientApp + '**/*.js'},
        report: report,

        /**
         * browser sync
         */
        browserReloadDelay: 1000,

        /**
         * template cache
         */
        templateCache: {
            file: 'templates.js',
            options: {
                module: 'app',
                // root: 'app/',
                // base: '.',
                standalone: false
            }
        },
        temp: temp,
        packages: packages,

        /**
         * specs.html, our HTML spec runner
         */
        specRunner: client + specRunnerFile,
        specRunnerFile: specRunnerFile,

        /**
         * The sequence of the injections into specs.html:
         *  1 testlibraries
         *      mocha setup
         *  2 bower
         *  3 js
         *  4 spechelpers
         *  5 specs
         *  6 templates
         */
        testlibraries: [
            nodeModules + '/mocha/mocha.js',
            nodeModules + '/chai/chai.js',
            nodeModules + '/sinon-chai/lib/sinon-chai.js'
        ],
        specHelpers: [client + 'test-helpers/*.js'],
        specs: [clientApp + '**/*.spec.js'],
        serverIntegrationSpecs: [client + '/tests/server-integration/**/*.spec.js'],

        defaultPort: 33610
    };

    for (var locale_idx in languages) {
        var lang = languages[locale_idx];
        config.locales[lang] = ['app/locales/*-' + lang + '.json', 'app/locales/fromResx/' + lang + '/*.json'];
    }

    /**
     * karma settings
     */
    config.karma = getKarmaOptions();

    return config;

    ////////////////

    function getKarmaOptions() {
        var options = {
            files: [].concat(
                'node_modules/jquery/dist/jquery.js',
                'node_modules/bootstrap/dist/js/bootstrap.min.js',
                'node_modules/bootstrap-material-design/dist/js/material.js',
                'node_modules/bootstrap-material-design/dist/js/ripples.js',
                'node_modules/lodash/lodash.min.js',
                'node_modules/api-check/dist/api-check.min.js',
                'node_modules/angular/angular.js',
                'node_modules/angular-resource/angular-resource.min.js',
                'node_modules/angular-cookies/angular-cookies.js',
                'node_modules/angular-messages/angular-messages.min.js',
                'node_modules/angular-ui-bootstrap/dist/ui-bootstrap-tpls.js',
                'node_modules/angular-ui-router/release/angular-ui-router.min.js',
                'node_modules/angular-smart-table/dist/smart-table.min.js',
                'node_modules/ng-table/dist/ng-table.min.js',
                'node_modules/angular-gettext/dist/angular-gettext.min.js',
                'node_modules/angular-formly/dist/formly.min.js',
                'node_modules/angular-formly-templates-bootstrap/dist/angular-formly-templates-bootstrap.min.js',
                'node_modules/bootstrap-ui-datetime-picker/dist/datetime-picker.min.js',
                'node_modules/bootstrap-ui-datetime-picker/dist/datetime-picker.tpls.js',
                'node_modules/d3/d3.min.js',
                'node_modules/nvd3/build/nv.d3.min.js',
                'node_modules/angular-nvd3/dist/angular-nvd3.min.js',
                'node_modules/toastr/build/toastr.min.js',

                'node_modules/angular-mocks/angular-mocks.js',
                config.specHelpers,
                clientApp + '**/*.module.js',
                clientApp + '**/*.service.js',
                clientApp + '**/*.directive.js',
                clientApp + '**/*.js',
                'js/**/*.js',

                temp + config.templateCache.file,
                'test/**/*Spec.js',
                config.serverIntegrationSpecs
            ),
            exclude: [],
            coverage: {
                dir: report + 'coverage',
                reporters: [
                    // reporters not supporting the `file` property
                    {type: 'html', subdir: 'report-html'},
                    {type: 'lcov', subdir: 'report-lcov'},
                    {type: 'text-summary'} //, subdir: '.', file: 'text-summary.txt'}
                ]
            },
            preprocessors: {}
        };
        options.preprocessors[clientApp + '**/!(*.spec)+(.js)'] = ['coverage'];
        return options;
    }

};
