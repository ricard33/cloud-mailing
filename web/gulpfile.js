/* eslint strict: 0, no-implicit-global: 0 */
/* eslint-env node */
/* eslint-disable angular/typecheck-object */

'use strict';

var browserSync = require('browser-sync');
var del = require('del');
var glob = require('glob');
var gulp = require('gulp');
var autoprefixer = require('gulp-autoprefixer');
var minifycss = require('gulp-clean-css');
var concat = require('gulp-concat');
var jsonminify = require('gulp-jsonminify');
var $ = require('gulp-load-plugins')({lazy: true});
var merge = require('gulp-merge-json');
var notify = require('gulp-notify');
var sass = require('gulp-sass');
var uglify = require('gulp-uglify');
var args = require('yargs');
var config = require('./gulp.config')();
var port = process.env.PORT || config.defaultPort;

/**
 * yargs variables can be passed in to alter the behavior, when present.
 * Example: gulp serve-dev
 *
 * --verbose  : Various tasks will produce more output to the console.
 * --nosync   : Don't launch the browser with browser-sync when serving code.
 * --debug    : Launch debugger with node-inspector.
 * --debug-brk: Launch debugger and break on 1st line with node-inspector.
 * --startServers: Will start servers for midway tests on the test task.
 */

/**
 * List the available gulp tasks
 */
gulp.task('help', $.taskListing);
gulp.task('default', ['help']);

/**
 * vet the code and create coverage report
 * @return {Stream}
 */
gulp.task('vet', function () {
    log('Analyzing source with ESLint');

    return gulp
        .src(config.alljs)
        .pipe($.if(args.verbose, $.print()))
        // eslint() attaches the lint output to the "eslint" property
        // of the file object so it can be used by other modules.
        .pipe($.eslint())
        // eslint.format() outputs the lint results to the console.
        // Alternatively use eslint.formatEach() (see Docs).
        .pipe($.eslint.format())
        // To have the process exit with an error code (1) on
        // lint error, return the stream and pipe to failAfterError last.
        .pipe($.eslint.failAfterError());
});

/**
 * Create a visualizer report
 */
gulp.task('plato', function (done) {
    log('Analyzing source with Plato');
    log('Browse to /report/plato/index.html to see Plato results');

    startPlatoVisualizer(done);
});

gulp.task('css', ['clean-styles'], function () {
    return gulp.src(config.scss_compile)
        .pipe(sass(config.gulpSassOptions))
        .on("error", notify.onError(function (error) {
            return "Error: " + error.message;
        }))
        .pipe(concat(config.css))
        .pipe(autoprefixer('last 2 versions'))
        .pipe(gulp.dest(config.temp))
        ;
});

// Fonts
gulp.task('fonts', function () {
    return gulp.src(config.fonts)
        .pipe(gulp.dest(config.build + '/fonts'));
});

// Images
gulp.task('images', function () {
    log('Compressing and copying images');
    return gulp.src(config.images)
        .pipe($.imagemin({optimizationLevel: 4}))
        .pipe(gulp.dest(config.build + '/img'))
        ;
});

var gulpLocale = function (lang) {
    gulp.task('locale_' + lang, function () {
        return gulp.src(config.locales[lang])
            .pipe(merge('locale-' + lang + '.json'))
            .pipe(jsonminify())
            .pipe(gulp.dest(config.build + '/locales'))
            ;
    });
};

// Locales
for (var locale_idx in config.languages) {
    var lang = config.languages[locale_idx];
    gulpLocale(lang);
}

gulp.task('locales', Array.prototype.map.call(config.languages, function (x) {
    return 'locale_' + x;
}));


// Clean
gulp.task('clean', function (cb) {
    del(config.build + '/**', {force: true}, cb);
});


/**
 * Remove all files from the build, temp, and reports folders
 * @param  {Function} done - callback when complete
 */
gulp.task('clean', function (done) {
    var delconfig = [].concat(config.build, config.temp);
    log('Cleaning: ' + $.util.colors.blue(delconfig));
    del(delconfig, {force: true}, done);
});

/**
 * Remove all fonts from the build folder
 * @param  {Function} done - callback when complete
 */
gulp.task('clean-fonts', function (done) {
    clean(config.build + 'fonts/**/*.*', done);
});

/**
 * Remove all images from the build folder
 * @param  {Function} done - callback when complete
 */
gulp.task('clean-images', function (done) {
    clean(config.build + 'img/**/*.*', done);
});

/**
 * Remove all styles from the build and temp folders
 * @param  {Function} done - callback when complete
 */
gulp.task('clean-styles', function (done) {
    var files = [].concat(
        config.temp + '**/*.css',
        config.build + 'css/**/*.css'
    );
    clean(files, done);
});

/**
 * Remove all js and html from the build and temp folders
 * @param  {Function} done - callback when complete
 */
gulp.task('clean-code', function (done) {
    var files = [].concat(
        config.temp + '**/*.js',
        config.build + 'js/**/*.js',
        config.build + '**/*.html'
    );
    clean(files, done);
});

/**
 * Create $templateCache from the html templates
 * @return {Stream}
 */
gulp.task('templatecache', ['clean-code'], function () {
    log('Creating an AngularJS $templateCache');

    return gulp
        .src(config.html)
        .pipe($.if(args.verbose, $.bytediff.start()))
        .pipe($.minifyHtml({empty: true}))
        .pipe($.if(args.verbose, $.bytediff.stop(bytediffFormatter)))
        .pipe($.angularTemplatecache(
            config.templateCache.file,
            config.templateCache.options
        ))
        .pipe(gulp.dest(config.temp));
});

gulp.task('inject', ['css', 'templatecache'], function () {
    log('Wire up css ans js into the html, after files are ready');
    return gulp
        .src(config.index)
        .pipe(inject([config.temp + config.css].concat(config.js)))
        .pipe(gulp.dest(config.temp));
});

/**
 * Build everything
 * This is separate so we can run tests on
 * optimize before handling image or fonts
 */
gulp.task('build', ['optimize', 'images', 'fonts', 'locales'], function () {
    log('Building everything');

    var msg = {
        title: 'gulp build',
        subtitle: 'Deployed to the build folder',
        message: 'Running `gulp serve-build`'
    };
    // del(config.temp);
    log(msg);
    notify(msg);
});

/**
 * Optimize all files, move to a build folder,
 * and inject them into the new index.html
 * @return {Stream}
 */
gulp.task('optimize', ['inject'/*, 'test'*/], function () {
    log('Optimizing the js, css, and html');

    // Filters are named for the gulp-useref path
    var cssFilter = $.filter(config.build + '**/*.css', {restore: true});
    var jsAppFilter = $.filter(config.build + '**/' + config.optimized.app, {restore: true});
    var jslibFilter = $.filter(config.build + '**/' + config.optimized.lib, {restore: true});
    var notIndexFilter = $.filter([config.build + '**/*', '!' + config.build + '**/index.html'], {restore: true});

    var templateCache = config.temp + config.templateCache.file;

    return gulp
        .src(config.temp + config.index)
        // .pipe($.plumber())
        .pipe(inject(templateCache, 'templates'))

        .pipe($.useref({searchPath: ['.', './app'], base: config.build}))

        // Get the css
        .pipe(cssFilter)
        .pipe(minifycss({keepSpecialComments: 0}))
        .pipe(cssFilter.restore)

        // Get the custom javascript
        .pipe(jsAppFilter)
        .pipe($.ngAnnotate({add: true}))
        .pipe(uglify({mangle: false})
            .on("error", notify.onError(function (error) {
                return "Error: " + error.message;
            }))
        )
        // .pipe(getHeader())
        .pipe(jsAppFilter.restore)

        // Get the vendor javascript
        .pipe(jslibFilter)
        .pipe(uglify({mangle: false})
            .on("error", notify.onError(function (error) {
                return "Error: " + error.message;
            }))
        )
        .pipe(jslibFilter.restore)

        // Take inventory of the file names for future rev numbers
        .pipe(notIndexFilter)
        .pipe($.print())
        .pipe($.rev())
        .pipe(notIndexFilter.restore)

        // Replace the file names in the html with rev numbers
        .pipe($.revReplace())
        .pipe(gulp.dest(config.build));
});

/**
 * Run specs once and exit
 * To start servers and run midway specs as well:
 *    gulp test --startServers
 * @return {Stream}
 */
// gulp.task('test', ['vet', 'templatecache'], function (done) {
gulp.task('test', [], function (done) {
    startTests(true /*singleRun*/, done);
});

/**
 * Run specs and wait.
 * Watch for file changes and re-run tests on each change
 * To start servers and run midway specs as well:
 *    gulp autotest --startServers
 */
gulp.task('autotest', function (done) {
    startTests(false /*singleRun*/, done);
});

/**
 * serve the dev environment
 * --debug-brk or --debug
 * --nosync
 */
gulp.task('serve-dev', ['inject', 'locales', 'fonts'], function () {
    return startBrowserSync(true /*isDev*/);
});

/**
 * serve the build environment
 * --debug-brk or --debug
 * --nosync
 */
gulp.task('serve-build', ['build'], function () {
    return startBrowserSync(false /*isDev*/);
});

/**
 * Bump the version
 * --type=pre will bump the prerelease version *.*.*-x
 * --type=patch or no flag will bump the patch version *.*.x
 * --type=minor will bump the minor version *.x.*
 * --type=major will bump the major version x.*.*
 * --version=1.2.3 will bump to a specific version and ignore other flags
 */
gulp.task('bump', function () {
    var msg = 'Bumping versions';
    var type = args.type;
    var version = args.ver;
    var options = {};
    if (version) {
        options.version = version;
        msg += ' to ' + version;
    } else {
        options.type = type;
        msg += ' for a ' + type;
    }
    log(msg);

    return gulp
        .src(config.packages)
        .pipe($.print())
        .pipe($.bump(options))
        .pipe(gulp.dest(config.root));
});

/**
 * Optimize the code and re-load browserSync
 */
gulp.task('browserSyncReload', ['optimize'], browserSync.reload);

////////////////


/**
 * When files change, log it
 * @param  {Object} event - event that fired
 */
function changeEvent(event) {
    var srcPattern = new RegExp('/.*(?=/' + config.source + ')/');
    log('File ' + event.path.replace(srcPattern, '') + ' ' + event.type);
}

/**
 * Delete all files in a given path
 * @param  {Array}   path - array of paths to delete
 * @param  {Function} done - callback when complete
 */
function clean(path, done) {
    log('Cleaning: ' + $.util.colors.blue(path));
    del(path, {force: true}, done);
}

/**
 * Inject files in a sorted sequence at a specified inject label
 * @param   {Array} src   glob pattern for source files
 * @param   {String} label   The label name
 * @param   {Array} order   glob pattern for sort order of the files
 * @returns {Stream}   The stream
 */
function inject(src, label, order) {
    var options = {
        relative: false,
        ignorePath: ['..', '/static', '/app']
    };
    if (label) {
        options.name = 'inject:' + label;
    }

    return $.inject(orderSrc(src, order), options);
}

/**
 * Order a stream
 * @param   {Stream} src   The gulp.src stream
 * @param   {Array} order Glob array pattern
 * @returns {Stream} The ordered stream
 */
function orderSrc(src, order) {
    //order = order || ['**/*'];
    return gulp
        .src(src, {read: false})
        .pipe($.if(order, $.order(order)));
}

/**
 * Start BrowserSync
 * --nosync will avoid browserSync
 * @param  {Boolean} isDev - dev or build mode
 * @param  {Boolean} specRunner - server spec runner html
 */
function startBrowserSync(isDev, specRunner) {
    if (args.nosync || browserSync.active) {
        return;
    }

    log('Starting BrowserSync on port ' + port);

    // If build: watches the files, builds, and restarts browser-sync.
    // If dev: watches scss, compiles it to css, browser-sync handles reload
    if (isDev) {
        gulp.watch(config.scss, ['css'])
            .on('change', changeEvent);
        gulp.watch([config.index], ['inject'])
            .on('change', changeEvent);
    } else {
        gulp.watch([config.scss, config.js, config.html], ['browserSyncReload'])
            .on('change', changeEvent);
    }

    var options = {
        proxy: {
            target: 'https://localhost:' + port,
            ws: true
        },
        // server: {
        //     baseDir: [config.clientApp, '.', '../static'],
        //     index: '../' + config.temp + 'index.html'
        // },
        port: 3000,
        online: true,
        files: isDev ? [
            config.temp + 'index.html',
            config.clientApp + '**/*.*',
            '' + config.images,
            '!' + config.scss,
            config.temp + '**/*.css'
        ] : [],
        ghostMode: { // these are the defaults t,f,t,t
            clicks: false,
            location: false,
            forms: false,
            scroll: false
        },
        open: false,
        injectChanges: true,
        logFileChanges: true,
        logLevel: 'info',
        logPrefix: 'hottowel',
        notify: true,
        reloadDelay: 0 //1000
    };
    if (specRunner) {
        options.startPath = config.specRunnerFile;
    }

    return browserSync(options);
}

/**
 * Start Plato inspector and visualizer
 */
function startPlatoVisualizer(done) {
    log('Running Plato');

    var files = glob.sync(config.plato.js);
    var excludeFiles = /.*\.spec\.js/;
    var plato = require('plato');

    var options = {
        title: 'Plato Inspections Report',
        exclude: excludeFiles
    };
    var outputDir = config.report + '/plato';

    plato.inspect(files, outputDir, options, platoCompleted);

    function platoCompleted(report) {
        var overview = plato.getOverviewReport(report);
        if (args.verbose) {
            log(overview.summary);
        }
        if (done) {
            done();
        }
    }
}

/**
 * Start the tests using karma.
 * @param  {boolean} singleRun - True means run once and end (CI), or keep running (dev)
 * @param  {Function} done - Callback to fire when karma is done
 * @return {undefined}
 */
function startTests(singleRun, done) {
    var child;
    var excludeFiles = [];
    var fork = require('child_process').fork;
    var Karma = require('karma').Server;
    var serverSpecs = config.serverIntegrationSpecs;

    if (args.startServers) {
        log('Starting servers');
        var savedEnv = process.env;
        savedEnv.NODE_ENV = 'dev';
        savedEnv.PORT = 8888;
        child = fork(config.nodeServer);
    } else {
        if (serverSpecs && serverSpecs.length) {
            excludeFiles = serverSpecs;
        }
    }

    new Karma({
        configFile: __dirname + '/karma.conf.js',
        exclude: excludeFiles,
        singleRun: !!singleRun
    }, karmaCompleted).start();

    ////////////////

    function karmaCompleted(karmaResult) {
        log('Karma completed');
        if (child) {
            log('shutting down the child process');
            child.kill();
        }
        if (karmaResult === 1) {
            done('karma: tests failed with code ' + karmaResult);
        } else {
            done();
        }
    }
}

/**
 * Formatter for bytediff to display the size changes after processing
 * @param  {Object} data - byte data
 * @return {String}      Difference in bytes, formatted
 */
function bytediffFormatter(data) {
    var difference = data.savings > 0 ? ' smaller.' : ' larger.';
    return data.fileName + ' went from ' +
        (data.startSize / 1000).toFixed(2) + ' kB to ' +
        (data.endSize / 1000).toFixed(2) + ' kB and is ' +
        formatPercent(1 - data.percent, 2) + '%' + difference;
}

/**
 * Format a number as a percentage
 * @param  {Number} num       Number to format as a percent
 * @param  {Number} precision Precision of the decimal
 * @return {String}           Formatted perentage
 */
function formatPercent(num, precision) {
    return (num * 100).toFixed(precision);
}

/**
 * Log a message or series of messages using chalk's blue color.
 * Can pass in a string, object or array.
 */
function log(msg) {
    if (typeof msg === 'object') {
    for (var item in msg) {
        if (msg.hasOwnProperty(item)) {
            $.util.log($.util.colors.blue(msg[item]));
        }
    }
} else {
    $.util.log($.util.colors.blue(msg));
}
}
